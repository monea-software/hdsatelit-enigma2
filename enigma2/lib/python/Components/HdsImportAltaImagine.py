# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImportAltaImagine.py: la prima pornire a imaginii, cand nu e nicio copie HD Satelit de pus la loc, canalele si
# setarile din copia altei imagini Enigma2, numai dupa o intrebare.
#
# Drumul:
#   1. tools/enigma2.sh.in ruleaza Components/HdsCopieSetari.py pornire inainte de enigma2. La prima pornire a unei
#      imagini proaspat scrise (fara settings si fara semnul "gata" al trusei), cand dupa asteptarea stick-ului nu e
#      nicio copie HD Satelit a acestui model, pornire() scrie aici starea CAUTA (marcheaza_cautarea), fara alta
#      cautare: pornirea receptorului nu se lungeste.
#   2. Dupa pornirea sesiunii (HdsCopieSetari.porneste -> porneste): cautarea surselor a importului existent
#      (HdsImportSurse.porneste_cautarea, pe firul ei; aceeasi stare ca ecranul "Import canale și setări" si pagina
#      web /import). Se alege prima sursa buna (alege_sursa): pe un stick sau un disc, cu lista de canale, nu o copie
#      HD Satelit (sub hdsatelit/: pe aceea o pune la loc pornire(), cand e a acestui model). Fara asa ceva: starea
#      NIMIC, nimic pe ecran.
#   3. Cu o sursa: starea INTREBARE si intrebarea pe televizor, prin coada de notificari (se deschide cand InfoBar e
#      in fata, deci dupa asistentul de pornire si dupa meniul pe care il deschide), cu "Da" ales; aceeasi intrebare
#      in web (pagina /import si banda de pe prima pagina). Raspunsul dat intr-o parte inchide intrebarea din cealalta.
#      Nu (si EXIT, care la caseta de mesaj inseamna Nu) = starea NU: nu se mai intreaba, importul ramane in meniu.
#      Fara raspuns (interfata repornita inainte), la urmatoarea pornire a interfetei se cauta si se intreaba din nou.
#   4. Da = importul existent (HdsImportSurse.porneste_importul) cu alegerile primei porniri (ALEGERI_PRIMA):
#      canalele si buchetele, setarile antenei si inregistrarile programate, cele pe care copia le are; fara limba si
#      setarile generale (cheile difera intre imagini, iar limba s-a ales in asistent). Copia de siguranta, arhivele,
#      limitele si lista alba sunt ale importului.
#   5. La capat: starea GATA cu rezumatul (ce s-a adus, cu numere, si ce nu), aratat o data pe televizor si in web;
#      cand setarile antenei asteapta repornirea interfetei, televizorul intreaba apoi daca o reporneste acum.
# Starea sta in /home/root/hds-restaurare/alta-imagine.json (dosarul restaurarii HD Satelit, in afara /etc/enigma2:
# o resetare la valorile din fabrica nu o aduce inapoi), scrisa atomic: starea, numere si calea copiei, fara valori din
# settings. Variabila HDS_RADACINA e numai pentru probe, ca la HdsCopieSetari.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import json
import os
import re
import time

# acelasi dosar ca HdsCopieSetari.DOSAR_RESTAURARE (un test le compara)
DOSAR_RESTAURARE = "home/root/hds-restaurare"
FISIER_STARE = "alta-imagine.json"
MAX_STARE = 64 * 1024
CALE_ETC = "/etc/enigma2"

CAUTA = "cauta"            # prima pornire fara copie HD Satelit: de cautat dupa pornirea sesiunii
INTREBARE = "intrebare"    # sursa gasita, intrebarea deschisa pe televizor si in web
DA = "da"                  # raspunsul a fost Da, importul lucreaza
GATA = "gata"              # importul s-a terminat; rezumatul e in stare
NU = "nu"                  # raspunsul a fost Nu: nu se mai intreaba
NIMIC = "nimic"            # cautarea nu a gasit nicio copie a altei imagini
STARI = (CAUTA, INTREBARE, DA, GATA, NU, NIMIC)
DESCHISE = (CAUTA, INTREBARE)

MEDII_BUNE = ("stick", "disc")
# copiile HD Satelit stau pe mediu sub HdsCopieSetari.DOSAR_PE_MEDIU ("hdsatelit/copii-setari")
PREFIX_COPII_HDS = "hdsatelit/"
ALEGERI_PRIMA = {"canale": True, "tunere": True, "temporizatoare": True, "generale": False}
MAX_TEXT_SURSA = 70
# tipurile de serviciu radio din lamedb (al cincilea camp al randului serviciului): 2 = radio, 10 = radio AAC
TIPURI_RADIO = (2, 10)
TIPAR_BUCHET_INDEX = re.compile(r'^#SERVICE\s+1:7:\d+:.*FROM BOUQUET "', re.I)
TIPAR_TIMER = re.compile(r"<timer[\s>/]")
PREFIX_BUCHET_IMAGINE = "userbouquet.hds_"   # acelasi ca HdsImportSurse.PREFIX_BUCHET_IMAGINE (un test le compara)


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsImportAltaImagine] %s" % text)


# ---------------------------------------------------------------- starea pe disc

def radacina(rad=None):
	if rad:
		return rad
	return os.environ.get("HDS_RADACINA") or "/"


def cale_stare(rad=None):
	return os.path.join(radacina(rad), *(DOSAR_RESTAURARE.split("/") + [FISIER_STARE]))


def citeste_starea(rad=None):
	"""Starea din fisier ({"stare", "cand", "sursa", "rezumat", ...}); {} cand lipseste sau nu se poate citi."""
	try:
		with open(cale_stare(rad), "rb") as f:
			date = f.read(MAX_STARE + 1)
	except (OSError, IOError):
		return {}
	if len(date) > MAX_STARE:
		return {}
	try:
		st = json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return {}
	if not isinstance(st, dict) or st.get("stare") not in STARI:
		return {}
	return st


def scrie_starea(st, rad=None):
	"""Scrie starea atomic (.nou, fsync, os.replace), drepturi 0600. True daca a mers."""
	cale = cale_stare(rad)
	nou = cale + ".nou"
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		date = json.dumps(st, ensure_ascii=True, sort_keys=True).encode("ascii")
		fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
		return True
	except (OSError, IOError, TypeError, ValueError) as eroare:
		_jurnal("starea nu s-a putut scrie: %s" % eroare.__class__.__name__)
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def _schimba(rad=None, **campuri):
	st = citeste_starea(rad)
	st.update(campuri)
	st["cand"] = int(time.time())
	scrie_starea(st, rad)
	return st


def marcheaza_cautarea(rad=None):
	"""Din HdsCopieSetari.pornire(), la prima pornire fara copie HD Satelit: starea CAUTA, numai daca nu s-a raspuns
	inca (Nu, Da, sau o cautare fara rezultat nu se intorc). True daca s-a scris."""
	st = citeste_starea(rad)
	if st and st.get("stare") not in DESCHISE:
		return False
	return scrie_starea({"stare": CAUTA, "cand": int(time.time())}, rad)


# ---------------------------------------------------------------- alegerea sursei

def _rel(s):
	return (s.get("rel") or "").replace("\\", "/").lstrip("/")


def sursa_potrivita(s):
	"""O sursa pentru intrebarea primei porniri: pe un stick sau un disc, cu lista de canale (lamedb in formatul pe
	care il citeste imaginea), nu o copie HD Satelit."""
	if not isinstance(s, dict) or s.get("mediu") not in MEDII_BUNE or not s.get("canale"):
		return False
	if not s.get("lamedb", True):
		return False
	return not _rel(s).lower().startswith(PREFIX_COPII_HDS)


def alege_sursa(surse):
	"""Prima sursa potrivita, in ordinea importului (stick-urile intai, pe fiecare cele mai noi intai): aceeasi pe care
	o alege si ecranul "Import canale și setări". None cand nu e niciuna."""
	for s in surse or []:
		if sursa_potrivita(s):
			return s
	return None


def alegeri_prima(sursa):
	"""Alegerile importului la prima pornire, fara cele pe care sursa nu le poate da."""
	from Components import HdsImportSurse
	return HdsImportSurse.alegeri_efective(ALEGERI_PRIMA, sursa)


# ---------------------------------------------------------------- numerele rezumatului

def numara_canale(cale):
	"""(canale TV, posturi de radio) din lamedb (formatul 4: dupa "services", cate trei randuri pe serviciu, al cincilea
	camp al primului rand e tipul). (0, 0) cand fisierul lipseste sau nu e bun."""
	tv = radio = 0
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			if not f.readline().startswith("eDVB services /"):
				return 0, 0
			in_servicii = False
			rand_serviciu = 0
			for rand in f:
				rand = rand.rstrip("\r\n")
				if not in_servicii:
					if rand == "services":
						in_servicii = True
					continue
				if rand == "end":
					break
				if rand_serviciu == 0:
					parti = rand.split(":")
					try:
						tip = int(parti[4])
					except (IndexError, ValueError):
						continue
					if tip in TIPURI_RADIO:
						radio += 1
					else:
						tv += 1
				rand_serviciu = (rand_serviciu + 1) % 3
	except (OSError, IOError):
		return 0, 0
	return tv, radio


def numara_buchete(dosar):
	"""Listele de canale din bouquets.tv si bouquets.radio (randurile "FROM BOUQUET"), cum le vede omul, fara listele
	imaginii (userbouquet.hds_*: DAB+ si DVB-T2 din satelit), pe care importul le pastreaza, nu le aduce."""
	n = 0
	for nume in ("bouquets.tv", "bouquets.radio"):
		try:
			with open(os.path.join(dosar, nume), "r", encoding="utf-8", errors="replace") as f:
				n += sum(1 for rand in f if TIPAR_BUCHET_INDEX.match(rand.strip())
					and '"' + PREFIX_BUCHET_IMAGINE not in rand)
		except (OSError, IOError):
			continue
	return n


def numara_temporizatoare(cale):
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return len(TIPAR_TIMER.findall(f.read(8 * 1024 * 1024)))
	except (OSError, IOError):
		return 0


def fa_rezumatul(rez, alegeri, sursa, dosar_etc=None):
	"""Rezumatul pastrat in stare (numai numere si texte de jurnal), din rezultatul importului si din fisierele scrise."""
	dosar_etc = dosar_etc or CALE_ETC
	rez = rez if isinstance(rez, dict) else {}
	r = {
		"ok": bool(rez.get("ok")),
		"tv": 0, "radio": 0, "buchete": 0, "temporizatoare": 0,
		"setari": int(rez.get("setari") or 0),
		"copia_setari": bool(sursa and sursa.get("setari")),
		"copia_temporizatoare": bool(sursa and sursa.get("temporizatoare")),
		"mesaje": [str(m)[:300] for m in (rez.get("mesaje") or [])][:12],
	}
	if rez.get("canale"):
		r["tv"], r["radio"] = numara_canale(os.path.join(dosar_etc, "lamedb"))
		r["buchete"] = numara_buchete(dosar_etc)
	if rez.get("temporizatoare") and alegeri.get("temporizatoare"):
		r["temporizatoare"] = numara_temporizatoare(os.path.join(dosar_etc, "timers.xml"))
	r["repornire"] = r["setari"] > 0
	return r


# ---------------------------------------------------------------- textele

def text_sursa_scurt(s):
	"""Mediul si calea copiei (de pilda: Stick USB "X": backup/enigma2settingsbackup.tar.gz), cu calea taiata la
	stanga cand e prea lunga."""
	from Components import HdsImportSurse
	text = HdsImportSurse.text_sursa(s)
	if len(text) > MAX_TEXT_SURSA:
		text = "…" + text[-(MAX_TEXT_SURSA - 1):]
	return "%s: %s" % (s.get("mediu_nume", ""), text)


def text_intrebare(s):
	return _("Am găsit canalele și setările din altă imagine. Le aduc?") + "\n" + text_sursa_scurt(s)


def parti_rezumat(r):
	"""(ce s-a adus, ce nu): doua liste de texte scurte, aceleasi pe televizor si in web."""
	adus = []
	if r.get("tv"):
		adus.append(_("canale TV: %d") % r["tv"])
	if r.get("radio"):
		adus.append(_("posturi de radio: %d") % r["radio"])
	if r.get("buchete"):
		adus.append(_("liste de canale: %d") % r["buchete"])
	if r.get("temporizatoare"):
		adus.append(_("înregistrări programate: %d") % r["temporizatoare"])
	if r.get("setari"):
		adus.append(_("setările antenei (intră după repornirea interfeței)"))
	neadus = []
	if not r.get("setari"):
		neadus.append(_("setările antenei (nu sunt în copie pentru un tuner de satelit)"))
	neadus.append(_("limba și celelalte setări ale meniului"))
	neadus.append(_("rețeaua și Wi-Fi"))
	neadus.append(_("pluginurile, skinul și piconurile"))
	neadus.append(_("modulele de acces condiționat"))
	return adus, neadus


def text_rezumat(r):
	"""Textul de pe televizor dupa import."""
	if r.get("intrerupt"):
		return _("Aducerea canalelor din altă imagine s-a oprit la o repornire a interfeței. Canalele se pot aduce "
			"oricând din Meniu, Scanare, Import canale și setări.")
	adus, neadus = parti_rezumat(r)
	if not r.get("ok") or not adus:
		randuri = [_("Nu am adus nimic din copia altei imagini.")]
		randuri += [m for m in r.get("mesaje") or [] if m][-2:]
		randuri.append(_("Canalele se pot aduce oricând din Meniu, Scanare, Import canale și setări."))
		return "\n".join(randuri)
	return "\n".join([_("Am adus: %s.") % ", ".join(adus), _("Nu am adus: %s.") % ", ".join(neadus)])


def text_repornire():
	return _("Setările antenei intră după repornirea interfeței. Repornesc acum?")


def banda_panou(rad=None):
	"""Textul benzii de pe prima pagina a interfetei web cat timp intrebarea e deschisa, altfel textul gol."""
	try:
		st = citeste_starea(rad)
	except Exception:
		return ""
	if st.get("stare") != INTREBARE:
		return ""
	return _("Am găsit canalele și setările din altă imagine. Alege pe pagina Import canale și setări dacă le aduc.")


def stare_publica(rad=None):
	"""Ce vede pagina web /import: starea, intrebarea si sursa (numai textele), rezumatul (texte)."""
	st = citeste_starea(rad)
	stare = st.get("stare") or ""
	rez = {"stare": stare}
	s = st.get("sursa")
	if stare in (INTREBARE, DA, GATA) and isinstance(s, dict):
		try:
			from Components import HdsImportSurse
			rez["sursa"] = {"text": HdsImportSurse.text_sursa(s), "mediu_nume": s.get("mediu_nume", ""),
				"descriere": HdsImportSurse.descriere_sursa(s)}
		except Exception:
			rez["sursa"] = {"text": "", "mediu_nume": "", "descriere": ""}
	if stare == INTREBARE:
		rez["intrebare"] = _("Am găsit canalele și setările din altă imagine. Le aduc?")
		rez["ce_se_aduce"] = _("Se aduc canalele și buchetele, setările antenei și înregistrările programate. Limba și "
			"celelalte setări rămân cele de acum.")
	if stare == GATA and isinstance(st.get("rezumat"), dict) and not st.get("vazut_web"):
		r = st["rezumat"]
		adus, neadus = parti_rezumat(r)
		rez["rezumat"] = {"ok": bool(r.get("ok")) and bool(adus), "adus": adus, "neadus": neadus,
			"text": text_rezumat(r), "repornire": bool(r.get("repornire"))}
	return rez


# ---------------------------------------------------------------- pe receptor (firul enigma2)

_SESIUNE = []    # sesiunea enigma2, pentru repornirea interfetei din raspunsul de pe televizor
_VII = []        # ceasul cautarii si importul in curs, tinute in viata pana la capat
_CLASA = []


def _clasa_intrebare():
	"""Caseta intrebarii: MessageBox cu Da/Nu, "Da" ales, care se inchide singura (fara raspuns) cand intrebarea s-a
	inchis din web. Clasa se face la prima folosire: la incarcarea fisierului nu se importa nimic din enigma2."""
	if _CLASA:
		return _CLASA[0]
	from enigma import eTimer
	from Screens.MessageBox import MessageBox

	class IntrebareAltaImagine(MessageBox):
		def __init__(self, session, sursa):
			# textul se face la deschidere, nu la capatul cautarii: intre timp omul poate alege alta limba in asistent
			MessageBox.__init__(self, session, text_intrebare(sursa), type=MessageBox.TYPE_YESNO, default=True)
			self.skinName = "MessageBox"
			self.setTitle(_("Canalele din altă imagine"))
			self._ceas = eTimer()
			try:
				self._legatura = self._ceas.timeout.connect(self._verifica)
			except AttributeError:
				self._ceas.callback.append(self._verifica)
			self._ceas.start(1000, False)
			self.onClose.append(self._ceas.stop)

		def _verifica(self):
			if citeste_starea().get("stare") != INTREBARE:
				self._ceas.stop()
				self.close(None)

	_CLASA.append(IntrebareAltaImagine)
	return IntrebareAltaImagine


def _scoate_din_coada():
	"""Intrebarea pusa in coada de notificari si inca neaparuta nu mai apare (s-a raspuns din web). Cu _CLASA goala
	nu e nimic de scos: punerea in coada (_pune_intrebarea) face intai clasa."""
	try:
		from Tools import Notifications
	except ImportError:
		return
	if not _CLASA:
		return
	for n in list(Notifications.notifications):
		if n[1] is _CLASA[0]:
			try:
				Notifications.notifications.remove(n)
			except ValueError:
				pass


def _pune_intrebarea(sursa):
	from Tools import Notifications
	_scoate_din_coada()
	Notifications.AddNotificationWithCallback(_raspuns_tv, _clasa_intrebare(), sursa)


def _raspuns_tv(da=None):
	if da is None:
		return    # inchisa din web sau la o noua cautare
	ok, mesaj = raspunde(bool(da), "televizor")
	if not ok and mesaj:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(mesaj, MessageBox.TYPE_INFO, 10, "HdsImportAltaImagine")


def _dupa_cautare(rad=None):
	"""Pe firul enigma2, la capatul cautarii surselor: alegerea si intrebarea, sau NIMIC fara mesaj."""
	from Components import HdsImportSurse
	st = citeste_starea(rad)
	if st.get("stare") not in DESCHISE:
		return
	sursa = alege_sursa(HdsImportSurse.stare().get("surse") or [])
	if sursa is None:
		_schimba(rad, stare=NIMIC, sursa=None)
		_jurnal("nicio copie a altei imagini pe stick-uri sau discuri; nimic de intrebat")
		return
	_schimba(rad, stare=INTREBARE, sursa=sursa)
	_jurnal("copie a altei imagini gasita: %s (%s); intreb" % (_rel(sursa), sursa.get("mediu")))
	_pune_intrebarea(sursa)


def _porneste_cautarea(rad=None):
	"""Cautarea comuna a importului si un ceas care asteapta capatul ei (cautarea poate fi pornita si de pagina web
	sau de ecranul importului: atunci rezultatul ei e folosit la fel)."""
	from enigma import eTimer
	from Components import HdsImportSurse
	inceput = time.time()
	HdsImportSurse.porneste_cautarea()
	ceas = eTimer()
	pastrat = [ceas]

	def verifica():
		st = HdsImportSurse.stare()
		if st.get("cauta") or not st.get("cand"):
			if time.time() - inceput < 120:
				return
		ceas.stop()
		if pastrat[0] in _VII:
			_VII.remove(pastrat[0])
		try:
			_dupa_cautare(rad)
		except Exception as eroare:
			_jurnal("dupa cautare: %s" % eroare)

	try:
		pastrat.append(ceas.timeout.connect(verifica))
	except AttributeError:
		ceas.callback.append(verifica)
	_VII.append(ceas)
	ceas.start(500, False)


def raspunde(da, de_unde="web", rad=None):
	"""Raspunsul la intrebare, de pe televizor sau din web, pe firul enigma2. (ok, mesaj)."""
	st = citeste_starea(rad)
	if st.get("stare") != INTREBARE:
		return False, _("Întrebarea nu mai este deschisă.")
	if not da:
		_schimba(rad, stare=NU)
		_scoate_din_coada()
		_jurnal("raspunsul: nu (%s)" % de_unde)
		return True, _("Bine. Canalele se pot aduce oricând din Meniu, Scanare, Import canale și setări.")
	from Components import HdsImportSurse
	sursa = st.get("sursa")
	if not isinstance(sursa, dict) or not os.path.exists(sursa.get("cale", "")):
		r = {"ok": False, "mesaje": [_("Copia nu mai este pe stick sau pe disc.")]}
		_schimba(rad, stare=GATA, rezumat=fa_rezumatul(r, {}, sursa if isinstance(sursa, dict) else {}))
		_scoate_din_coada()
		_arata_rezumatul(rad)
		return False, _("Copia nu mai este pe stick sau pe disc.")
	if HdsImportSurse.ocupat():
		return False, _("Un import e deja în curs. Așteaptă să se termine.")
	alegeri = alegeri_prima(sursa)

	def la_sfarsit(rezultat):
		try:
			_dupa_import(rezultat, alegeri, sursa, rad)
		except Exception as eroare:
			_jurnal("dupa import: %s" % eroare)

	_schimba(rad, stare=DA)
	lucrare = HdsImportSurse.porneste_importul(sursa, alegeri, la_sfarsit)
	if lucrare is None:
		_schimba(rad, stare=INTREBARE)
		return False, _("Un import e deja în curs. Așteaptă să se termine.")
	_scoate_din_coada()
	_jurnal("raspunsul: da (%s); importul a pornit, alegeri %s" % (de_unde,
		",".join(sorted(k for k, v in alegeri.items() if v))))
	return True, _("Se aduc canalele și setările...")


def _dupa_import(rezultat, alegeri, sursa, rad=None, dosar_etc=None):
	r = fa_rezumatul(rezultat, alegeri, sursa, dosar_etc or CALE_ETC)
	_schimba(rad, stare=GATA, rezumat=r, vazut_tv=False, vazut_web=False)
	_jurnal("importul s-a terminat: ok=%s tv=%d radio=%d buchete=%d temporizatoare=%d setari=%d" % (r["ok"], r["tv"],
		r["radio"], r["buchete"], r["temporizatoare"], r["setari"]))
	_arata_rezumatul(rad)


def _arata_rezumatul(rad=None):
	"""Rezumatul pe televizor, o singura data; apoi, cand setarile antenei asteapta, intrebarea repornirii."""
	st = citeste_starea(rad)
	r = st.get("rezumat")
	if st.get("stare") != GATA or not isinstance(r, dict) or st.get("vazut_tv"):
		return
	_schimba(rad, vazut_tv=True)
	from Tools import Notifications
	from Screens.MessageBox import MessageBox

	def dupa(*_a):
		if r.get("repornire") and r.get("ok"):
			Notifications.AddNotificationWithCallback(_dupa_intrebarea_repornirii, MessageBox, text_repornire(),
				type=MessageBox.TYPE_YESNO, default=True)

	Notifications.AddNotificationWithCallback(dupa, MessageBox, text_rezumat(r), type=MessageBox.TYPE_INFO)


def _dupa_intrebarea_repornirii(da=False):
	if not da or not _SESIUNE:
		return
	from Screens.Standby import TryQuitMainloop
	_SESIUNE[0].open(TryQuitMainloop, 3)


def ascunde_rezumatul_web(rad=None):
	st = citeste_starea(rad)
	if st.get("stare") == GATA:
		_schimba(rad, vazut_web=True)
	return True, ""


def porneste(session, rad=None):
	"""Din HdsCopieSetari.porneste (dupa pornirea sesiunii, din mytest.py). Nu arunca."""
	try:
		del _SESIUNE[:]
		_SESIUNE.append(session)
		st = citeste_starea(rad)
		stare = st.get("stare")
		if stare in DESCHISE:
			_porneste_cautarea(rad)
		elif stare == DA:
			# interfata s-a oprit in timpul importului: fisierele scrise raman, copia de siguranta e in /etc/enigma2
			_schimba(rad, stare=GATA, rezumat={"ok": False, "intrerupt": True}, vazut_tv=False, vazut_web=False)
			_arata_rezumatul(rad)
		elif stare == GATA:
			_arata_rezumatul(rad)
	except Exception as eroare:
		_jurnal("pornirea: %s" % eroare)
