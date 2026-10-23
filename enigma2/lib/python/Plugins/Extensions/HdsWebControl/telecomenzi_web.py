# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# telecomenzi_web.py: „Telecomenzi” in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Setari > Sistem & Dispozitive > Telecomenzi (Screens/HdsTelecomenzi.py). Aici, cu aceleasi date
# si reguli (Components/HdsTelecomenziDate.py) si aceleasi texte:
# - lista telecomenzilor asociate: Porneste/Opreste, Redenumeste, „Tastele neasociate: se opresc / trec”, tastele
#   asociate cu stergerea fiecareia, Sterge telecomanda, Sterge toate asocierile; exportul JSON si CSV;
# - cititorul de coduri si proba tastelor: pagina NUMAI asculta (captureListen), tastele merg si pe televizor, cel mult
#   120 de secunde (C++ taie oricum), cu anuntul „Pagina web vede tastele apăsate.” pe televizor la fiecare pornire
#   (vede si un PIN tastat pe televizor: de aceea termenul scurt si anuntul);
# - asocierea unei telecomenzi noi: captureOthers (telecomanda receptorului merge), anuntul „Asociere pornită din
#   browser”, aceeasi clasa D.Asociere, fiecare pas scris imediat (D.salveaza, incarca_in_mapper, apply);
# - telecomanda virtuala: clic pe desen = tasta ca de pe telecomanda receptorului (/api/remotecontrol, prin
#   eRCMapper.inject din plugin.py); tinut apasat = apasare lunga.
#
# Captura din C++ e una singura (revizia, P23): pagina o atinge (touch) si o opreste numai daca a pornit-o ea; cand o
# are ecranul de pe televizor, pagina raspunde 409 „Ecranul Telecomenzi e deschis pe televizor.” si nu i-o ia. Cat
# asociaza ecranul (captureOthers), pagina nu schimba asocierile (ecranul scrie fisierul la fiecare buton); altfel
# fisierul se citeste din nou inaintea oricarei schimbari, ca sa nu se scrie peste ecran.
#
# FARA ASTEPTARE LUNGA: proiectul cerea GET /api/telecomenzi/evenimente cu asteptare de pana la 25 s pe
# reactor.callLater; in reactorul enigma2 callLater se intarzie cand bucla n-are alt motiv sa se trezeasca (nota din
# ScreenshotResource, plugin.py). Aici tastele se prelucreaza pe loc, din semnalul rawKey (ca pe televizor), iar pagina
# cere starea la o secunda cat tine captura; fiecare cerere e si semnul de viata (touch). Fara cereri 20 de secunde
# (browser inchis, fila ascunsa), C++ opreste captura singur. Coada tastelor e in C++ si se goleste la oprire; pagina
# nu tine copie.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/telecomenzi                         lista, captura paginii (texte, butoane aprinse), tabelul Viper
#   POST /api/telecomenzi-captura?fel=cititor|proba|proba-noua|asociere|oprit
#   POST /api/telecomenzi-asociere?pas=inapoi|sari|gata|continua|anuleaza|proba|inchide[&pastreaza=0|1]
#   POST /api/telecomenzi-schimba?actiune=activa|neasociate|redenumeste|sterge-tasta|sterge|sterge-tot&id=&cod=&nume=
#   GET  /api/telecomenzi-export?format=json|csv  codurile pentru aplicatii
#   GET  /telecomenzi                             pagina (cu desenul SVG al telecomenzii, din /usr/share/enigma2)
#
# FIRUL: totul ruleaza pe firul enigma2 (reactorul e bucla enigma2); fisierul de asocieri are cel mult 1 MB. Functiile
# legate de rawKey si captureEnded nu arunca niciodata (le cheama C++ din keyEvent) si nu se scot din lista din
# interiorul unui semnal (revizia, P24): scoaterea se amana cu un eTimer.

import time

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

MOD_NIMIC, MOD_CITITOR, MOD_PROBA, MOD_ASOCIERE = "", "cititor", "proba", "asociere"
CALE_DESEN_SVG = None      # probele pun aici desenul; pe receptor: resolveFilename(SCOPE_SKIN_IMAGE, ...)
CALE_ASOCIERI = None       # probele pun aici fisierul; pe receptor: D.CALE_ASOCIERI
CALE_IR = "/proc/hisi/msp/ir"
MAPPER = None              # probele pun aici un eRCMapper fals
AMANA = None               # probele pun aici amanarea (altfel un eTimer de 0 ms)
ANUNTA = None              # probele pun aici anuntul de pe televizor (altfel Notifications.AddPopup)
ID_ANUNT = "hds_telecomenzi_web"
MAX_NUME = 48
MAX_ISTORIC = 9


def _(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC). Un text gol ramane
	gol (gettext ar da antetul fisierului .po)."""
	if not text:
		return text or ""
	try:
		import builtins
		f = builtins.__dict__.get("_")
		if f is not None and f is not _:
			return f(text)
	except Exception:
		pass
	return text


def _jurnal(text):
	print("[HdsWebControl] telecomenzi: %s" % text)


def _d():
	from Components import HdsTelecomenziDate
	return HdsTelecomenziDate


def _mapper():
	if MAPPER is not None:
		return MAPPER
	try:
		from enigma import eRCMapper
		return eRCMapper.getInstance()
	except Exception:
		return None


def _cale():
	return CALE_ASOCIERI or _d().CALE_ASOCIERI


def _cale_ir():
	return CALE_IR


_KEYIDS = {}


def _nume_taste():
	if not _KEYIDS:
		try:
			from keyids import KEYIDS
			_KEYIDS.update(KEYIDS)
		except Exception:
			pass
	return _KEYIDS


# ------------------------------------------------------------------ starea paginii (una singura: captura e una)
class _Stare(object):
	def __init__(self):
		self.goleste()
		self.proba = None           # proba se pastreaza intre porniri, ca pe televizor cat e deschis ecranul (P28)

	def goleste(self):
		self.mod = MOD_NIMIC
		self.captura = False        # captura din C++ e pornita de pagina
		self.ultimul = 0
		self.istoric = []
		self.ancora = None
		self.ev = None
		self.aprinse = set()
		self.asociere = None
		self.inainte = None
		self.rezultat = None
		self.ultim = None
		self.ultim_sarit = None
		self.asteapta = False       # asocierea oprita de un termen: „Continuă”
		self.gata = False           # asocierea terminata: rezumatul si intrebarea „Le probezi acum?”
		self.contor_ir = None
		self.ir = 0
		self.oprita = ""            # de ce s-a oprit captura (textul pentru pagina)
		self.date = None


S = _Stare()
_LEGAT = {"da": False}
_CEASURI = []


def _amana(f):
	"""f() dupa ce se termina chemarea de acum (niciodata din interiorul unui semnal)."""
	if AMANA is not None:
		AMANA(f)
		return
	try:
		from enigma import eTimer
		ceas = eTimer()

		def _gata():
			try:
				_CEASURI.remove(ceas)
			except ValueError:
				pass
			try:
				f()
			except Exception as eroare:
				_jurnal("amanare: %s" % eroare)
		ceas.callback.append(_gata)
		_CEASURI.append(ceas)
		ceas.start(0, True)
	except Exception:
		f()


def _anunta(text):
	"""Anuntul scurt de pe televizor (revizia, P25): cine se uita la televizor stie ca pagina web vede tastele."""
	if ANUNTA is not None:
		ANUNTA(text)
		return
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, 5, ID_ANUNT)
	except Exception as eroare:
		_jurnal("anuntul de pe televizor: %s" % eroare)


def _leaga(m):
	if _LEGAT["da"] or m is None:
		return
	m.rawKey.get().append(_taste)
	m.captureEnded.get().append(_oprita)
	_LEGAT["da"] = True


def _dezleaga():
	"""Scoate functiile din semnale (numai amanat, cand captura paginii s-a terminat)."""
	m = _mapper()
	if m is None or S.captura or not _LEGAT["da"]:
		return
	for semnal, f in ((m.rawKey, _taste), (m.captureEnded, _oprita)):
		lista = semnal.get()
		if f in lista:
			lista.remove(f)
	_LEGAT["da"] = False


def _captura_televizor(m):
	"""True daca o captura e pornita de altcineva (ecranul de pe televizor)."""
	return m is not None and not S.captura and m.getCaptureMode() != m.captureOff


# ------------------------------------------------------------------ tastele (din C++)
def _buton_ev(D, ev):
	"""Butonul Viper al unui eveniment: cel in care se traduce sau, de pe telecomanda receptorului, el insusi."""
	return D.DUPA_COD.get(ev["tinta"] if ev["tinta"] >= 0 else (ev["cod"] if ev["dispozitiv"] == D.NATIV else -1))


def _aprinde(D, ev, b):
	if b is None:
		return
	if ev["fel"] == D.ELIBERAT:
		S.aprinse.discard(b[0])
	elif ev["fel"] in (D.APASAT, D.TINUT, D.LUNG):
		S.aprinse = set([b[0]])


def _prelucreaza():
	"""Evenimentele noi din C++, prelucrate dupa modul paginii. Se cheama din rawKey si din fiecare cerere a paginii
	(acelasi numar `ultimul`, deci niciun eveniment nu se ia de doua ori)."""
	m = _mapper()
	if m is None or not S.captura:
		return
	D = _d()
	for t in m.getEvents(S.ultimul):
		ev = D.eveniment(t)
		if ev is None:
			continue
		S.ultimul = max(S.ultimul, ev["numar"])
		if S.contor_ir is not None:
			S.contor_ir.nativ(ev)
		b = _buton_ev(D, ev)
		if S.mod == MOD_CITITOR:
			S.ev = ev
			if S.ancora is None:
				S.ancora = D.ancora_ceas(ev)
			if ev["fel"] in (D.APASAT, D.LUNG, D.ASCII):
				S.istoric.append(D.rand_istoric(ev, keyids=_nume_taste(), ancora=S.ancora))
				S.istoric = S.istoric[-MAX_ISTORIC:]
			_aprinde(D, ev, b)
		elif S.mod == MOD_PROBA and S.proba is not None:
			S.proba.primeste(ev)
			S.ev = ev if b is not None else None
			_aprinde(D, ev, b)
		elif S.mod == MOD_ASOCIERE:
			_eveniment_asociere(D, ev)


def _eveniment_asociere(D, ev):
	a = S.asociere
	if a is None or S.gata:
		return
	b_inainte = a.buton_curent()
	rezultat = a.primeste(ev)
	if rezultat in ("asociat", "gata") and b_inainte is not None and ev["fel"] == D.ELIBERAT:
		S.ultim = (b_inainte, ev["cod"])
	if rezultat == "sarit":
		S.ultim_sarit = b_inainte
	if a.schimbat:
		_salveaza(D, S.date)
	if rezultat == "nimic":
		return
	S.rezultat = rezultat
	if a.stare == a.GATA:
		_termina()


def _taste(numar):
	"""rawKey: ruleaza in keyEvent(), deci nu are voie sa arunce."""
	try:
		_prelucreaza()
	except Exception as eroare:
		_jurnal("tasta %r nu a putut fi prelucrata: %s" % (numar, eroare))


def _oprita(motiv):
	"""captureEnded: numai captura paginii; scoaterea din semnale se amana (P24)."""
	try:
		if not S.captura:
			return
		D = _d()
		S.captura = False
		S.aprinse = set()
		if S.mod == MOD_ASOCIERE and S.asociere is not None and not S.gata:
			if motiv in (D.OPRIRE_FARA_TASTE, D.OPRIRE_TERMEN, D.OPRIRE_SEMN_VIATA):
				S.asteapta = True
		elif S.mod in (MOD_CITITOR, MOD_PROBA):
			S.oprita = _text_oprire(D, motiv)
		_amana(_dezleaga)
	except Exception as eroare:
		_jurnal("oprirea capturii: %s" % eroare)


def _text_oprire(D, motiv):
	if motiv == D.OPRIRE_SEMN_VIATA:
		return _("Captura s-a oprit: pagina nu a mai cerut nimic 20 de secunde.")
	if motiv in (D.OPRIRE_TERMEN, D.OPRIRE_FARA_TASTE):
		return _("Captura s-a oprit după termen.")
	return ""


# ------------------------------------------------------------------ fisierul de asocieri
def _incarca(D):
	"""(date, mesajul fisierului tradus sau '')."""
	date, sablon, argument = D.incarca_cu_sablon(_cale())
	return date, D.text_mesaj(sablon, argument, _) if sablon else ""


def _salveaza(D, date):
	eroare = D.salveaza(date, _cale())
	if eroare:
		_jurnal("asocierile nu s-au putut scrie (%s)" % eroare)
	m = _mapper()
	if m is not None:
		D.incarca_in_mapper(m, date)
		m.apply()
	return not eroare


# ------------------------------------------------------------------ pornirea si oprirea capturii
def _raspuns(corp, cod=200):
	corp["_cod"] = cod
	return corp


def porneste(fel):
	"""POST /api/telecomenzi-captura?fel=..."""
	m = _mapper()
	D = _d()
	if m is None:
		return _raspuns(dict(stare(), result=False, message=_("Receptorul nu are utilitarul telecomenzilor.")), 503)
	if fel == "oprit":
		return opreste()
	if fel not in ("cititor", "proba", "proba-noua", "asociere"):
		return _raspuns(dict(stare(), result=False, message=_("Felul capturii nu e cunoscut.")), 400)
	if _captura_televizor(m):
		return _raspuns(dict(stare(), result=False, message=_("Ecranul Telecomenzi e deschis pe televizor.")), 409)
	if S.captura:
		m.setCapture(m.captureOff, 0, 0, 0)      # schimbarea modului: intai se opreste captura paginii
	proba = S.proba
	S.goleste()
	S.proba = proba
	_leaga(m)
	S.ultimul = m.getLastSequence()
	if fel in ("cititor", "proba", "proba-noua"):
		ok = m.setCapture(m.captureListen, 0, D.TERMEN_TOTAL_CITITOR, D.TERMEN_SEMN_VIATA)
		if not ok:
			return _raspuns(dict(stare(), result=False, message=_("Cititorul nu poate porni acum.") if fel == "cititor"
				else _("Proba nu poate porni acum.")), 409)
		S.captura = True
		if fel == "cititor":
			S.mod = MOD_CITITOR
			S.contor_ir = D.ContorIR(0) if _exista(_cale_ir()) else None
		else:
			S.mod = MOD_PROBA
			if fel == "proba-noua" or S.proba is None:
				S.proba = D.Proba()
		_anunta(_("Pagina web vede tastele apăsate."))
		return dict(stare(), result=True, message="")
	# asocierea: fisierul citit din nou (ecranul poate sa-l fi schimbat), copia de dinainte pentru „nu pastra”
	S.date, _mesaj = _incarca(D)
	S.inainte = D.curata(D.de_scris(S.date))
	S.asociere = D.Asociere(S.date)
	ok = m.setCapture(m.captureOthers, D.TERMEN_FARA_TASTE, D.TERMEN_TOTAL_ASOCIERE, D.TERMEN_SEMN_VIATA)
	if not ok:
		S.goleste()
		S.proba = proba
		return _raspuns(dict(stare(), result=False, message=_("Asocierea nu poate porni acum.")), 409)
	S.captura = True
	S.mod = MOD_ASOCIERE
	S.contor_ir = D.ContorIR(0) if _exista(_cale_ir()) else None
	_anunta(_("Asociere pornită din browser"))
	return dict(stare(), result=True, message="")


def _exista(cale):
	try:
		import os
		return os.path.exists(cale)
	except Exception:
		return False


def opreste():
	"""Opreste numai captura paginii; pagina se intoarce la lista (proba ramane pentru „reia”)."""
	m = _mapper()
	if S.mod == MOD_ASOCIERE and S.asociere is not None and not S.gata and S.asociere.ident is not None:
		return _raspuns(dict(stare(), result=False, message=_("Păstrezi ce ai asociat până acum?"), intrebare="pastreaza"), 409)
	if m is not None and S.captura:
		m.setCapture(m.captureOff, 0, 0, 0)
	S.captura = False
	proba = S.proba
	S.goleste()
	S.proba = proba
	_amana(_dezleaga)
	return dict(stare(), result=True, message="")


def _termina():
	"""Asocierea gata: captura oprita, rezumatul, intrebarea „Le probezi acum?” (ca pe televizor)."""
	m = _mapper()
	S.gata = True
	if m is not None and S.captura:
		m.setCapture(m.captureOff, 0, 0, 0)
	S.captura = False
	_amana(_dezleaga)


def pas(actiune, pastreaza=None):
	"""POST /api/telecomenzi-asociere?pas=..."""
	D = _d()
	m = _mapper()
	a = S.asociere
	if S.mod != MOD_ASOCIERE or a is None:
		return _raspuns(dict(stare(), result=False, message=_("Nicio asociere în curs.")), 409)
	if actiune == "anuleaza":
		if a.ident is not None and not S.gata and pastreaza not in ("0", "1"):
			return _raspuns(dict(stare(), result=False, message=_("Păstrezi ce ai asociat până acum?"),
				intrebare="pastreaza"), 409)
		if pastreaza == "0" and S.inainte is not None and not S.gata:
			_salveaza(D, S.inainte)
		if m is not None and S.captura:
			m.setCapture(m.captureOff, 0, 0, 0)
		S.captura = False
		proba = S.proba
		S.goleste()
		S.proba = proba
		_amana(_dezleaga)
		return dict(stare(), result=True, message="")
	if S.gata:
		if actiune == "proba":
			S.proba = None
			return porneste("proba-noua")
		if actiune == "inchide":
			proba = S.proba
			S.goleste()
			S.proba = proba
			return dict(stare(), result=True, message="")
		return _raspuns(dict(stare(), result=False, message=_("Asocierea s-a terminat.")), 409)
	if actiune == "continua":
		if not S.asteapta:
			return _raspuns(dict(stare(), result=False, message=""), 409)
		if _captura_televizor(m):
			return _raspuns(dict(stare(), result=False, message=_("Ecranul Telecomenzi e deschis pe televizor.")), 409)
		_leaga(m)
		S.ultimul = m.getLastSequence()
		if not m.setCapture(m.captureOthers, D.TERMEN_FARA_TASTE, D.TERMEN_TOTAL_ASOCIERE, D.TERMEN_SEMN_VIATA):
			return _raspuns(dict(stare(), result=False, message=_("Asocierea nu poate porni acum.")), 409)
		S.captura = True
		S.asteapta = False
		if S.contor_ir is not None:
			S.contor_ir.reia(0)
		return dict(stare(), result=True, message="")
	if actiune == "inapoi":
		if a.inapoi():
			if a.schimbat:
				_salveaza(D, S.date)
			S.rezultat = None
		return dict(stare(), result=True, message="")
	if actiune == "sari":
		S.ultim_sarit = a.buton_curent()
		r = a.sari()
		if r != "nimic":
			S.rezultat = "sarit"
		if a.stare == a.GATA:
			_termina()
		return dict(stare(), result=True, message="")
	if actiune == "gata":
		if a.termina():
			_termina()
			return dict(stare(), result=True, message="")
		return _raspuns(dict(stare(), result=False, message=_("Gata merge după MENU.")), 409)
	return _raspuns(dict(stare(), result=False, message=_("Pasul nu e cunoscut.")), 400)


# ------------------------------------------------------------------ schimbarile din lista
def schimba(actiune, ident="", cod="", nume="", confirmat=""):
	"""POST /api/telecomenzi-schimba: aceleasi schimbari ca tastele colorate din lista de pe televizor."""
	D = _d()
	m = _mapper()
	if m is not None and m.getCaptureMode() == m.captureOthers and not S.captura:
		return _raspuns(dict(stare(), result=False, message=_("Ecranul Telecomenzi e deschis pe televizor.")), 409)
	if S.mod == MOD_ASOCIERE and not S.gata:
		return _raspuns(dict(stare(), result=False, message=_("Asocierea e în curs.")), 409)
	date, _mesaj = _incarca(D)       # din nou din fisier: ecranul l-a putut schimba
	if actiune == "sterge-tot":
		if confirmat != "1":
			return _raspuns(dict(stare(), result=False, message=_("Ștergi toate asocierile?"), intrebare="sterge-tot"), 409)
		D.sterge_tot(date)
		_salveaza(D, date)
		return dict(stare(), result=True, message=_("Toate asocierile au fost șterse."))
	t = D.gaseste(date, ident)
	if t is None:
		return _raspuns(dict(stare(), result=False, message=_("Telecomanda nu mai există.")), 404)
	if actiune == "activa":
		D.comuta_activa(date, ident)
	elif actiune == "neasociate":
		if D.comuta_neasociate(date, ident) is None:
			return _raspuns(dict(stare(), result=False, message=""), 400)
	elif actiune == "redenumeste":
		if not D.redenumeste(date, ident, (nume or "")[:MAX_NUME]):
			return _raspuns(dict(stare(), result=False, message=_("Numele telecomenzii nu poate fi gol.")), 400)
	elif actiune == "sterge-tasta":
		try:
			c = int(cod)
		except (TypeError, ValueError):
			return _raspuns(dict(stare(), result=False, message=""), 400)
		if not D.sterge_tasta(date, ident, c):
			return _raspuns(dict(stare(), result=False, message=_("Nicio tastă asociată.")), 404)
	elif actiune == "sterge":
		if confirmat != "1":
			return _raspuns(dict(stare(), result=False, message=_("Ștergi telecomanda „%s”?") % t["nume"],
				intrebare="sterge"), 409)
		D.sterge_telecomanda(date, ident)
	else:
		return _raspuns(dict(stare(), result=False, message=_("Schimbarea nu e cunoscută.")), 400)
	_salveaza(D, date)
	return dict(stare(), result=True, message="")


# ------------------------------------------------------------------ starea pentru pagina
def _text_telecomanda(D, t):
	fel = _("USB") if t["fel"] == "usb" else _("IR")
	n = len(set(t["taste"].values()))
	stare_t = _("activă") if t["activa"] else _("oprită")
	if n == 1:
		taste = _("o tastă asociată")
	else:
		taste = _("%d taste asociate") % n
	return "%s (%s), %s, %s" % (t["nume"], fel, taste, stare_t)


def _telecomenzi(D, date):
	rez = []
	for t in date["telecomenzi"]:
		taste = []
		for c, tinta in sorted(t["taste"].items(), key=lambda kv: D.ORDINE_ASOCIERE.index(D.DUPA_COD[kv[1]][0])):
			b = D.DUPA_COD[tinta]
			sursa = D.text_cod(c, _nume_taste()) if t["fel"] == "usb" else "0x%X" % c
			taste.append({"cod": c, "buton": b[0], "text": "%s = %s" % (_(b[1]), sursa)})
		rez.append({
			"id": t["id"], "nume": t["nume"], "fel": t["fel"], "activa": bool(t["activa"]),
			"dispozitiv": t.get("dispozitiv") or t.get("protocol") or "",
			"neasociate": t.get("neasociate", ""),
			"text": _text_telecomanda(D, t),
			"text_neasociate": (_("Tastele neasociate: se opresc") if t.get("neasociate") == "opresc"
				else _("Tastele neasociate: trec")) if t["fel"] == "usb" else "",
			"nota": (_("Tastele neasociate se opresc numai după ce sunt asociate OK, săgețile, EXIT și MENU.")
				if t["fel"] == "usb" and t.get("neasociate") == "opresc" and not D.navigare_completa(t) else ""),
			"taste": taste,
			"semne": sorted(set(D.DUPA_COD[v][0] for v in t["taste"].values())),
		})
	return rez


def _secunde(m):
	if m is None or m.getCaptureMode() == m.captureOff or not S.captura:
		return ""
	n = m.getCaptureSecondsLeft()
	if n < 0:
		return ""
	return _("Mai sunt %d secunde") % n


def _citeste_ir():
	if S.contor_ir is None:
		return
	try:
		with open(_cale_ir()) as f:
			S.ir = S.contor_ir.fereastra(f.read(8192))
	except (OSError, IOError):
		S.contor_ir = None


def _captura_cititor(D):
	randuri = []
	ev = S.ev
	mare = _("Apasă orice buton.")
	if ev is not None:
		b = _buton_ev(D, ev)
		if ev["fel"] == D.ASCII:
			mare = _("caracterul %s") % (repr(chr(ev["cod"])) if 0 < ev["cod"] < 0x110000 else ev["cod"])
		elif b is not None:
			mare = _(b[1])
		else:
			mare = D.nume_tasta(ev["cod"], _nume_taste()) or (_("cod %d") % ev["cod"])
		disp = ev["dispozitiv"]
		randuri.append(_("Dispozitiv: %s") % (_("telecomanda receptorului") + " (%s)" % disp if disp == D.NATIV else disp))
		if ev["fel"] != D.ASCII:
			randuri.append(_("Cod: %d (0x%X) %s") % (ev["cod"], ev["cod"], D.nume_tasta(ev["cod"], _nume_taste())))
		randuri.append(_("Felul: %s") % _(D.FELURI.get(ev["fel"], "")))
		if ev["scan"] >= 0:
			randuri.append(_("Cod brut USB (HID): 0x%X") % ev["scan"])
		if b is not None and disp != D.NATIV:
			randuri.append(_("Merge ca butonul %s al telecomenzii receptorului") % _(b[1]))
		if disp == D.NATIV and b is not None:
			randuri.append(_("IR: NEC, adresa 0x02 0xCD, comanda 0x%02X, KeyId 0x%08X") % (b[4], D.keyid_viper(b[4])))
	else:
		randuri.append(_("Tastele merg și pe televizor cât ascultă pagina; aici se arată codul lor."))
	if S.ir:
		randuri.append(_("Semnale IR pe care receptorul nu le folosește: %d") % S.ir)
		randuri.append(_("Receptorul a primit un semnal de la altă telecomandă, dar nu îl poate citi încă."))
	return {"titlu": _("Cititor de coduri"), "mare": mare, "detalii": randuri, "istoric": list(reversed(S.istoric))}


def _captura_proba(D):
	p = S.proba
	if p.gata():
		mare = _("Toate butoanele merg.")
	else:
		mare = _("%d din %d de butoane verificate") % (len(p.verificate), D.NUMAR_BUTOANE)
	randuri = []
	ramase = p.ramase()
	if ramase:
		randuri.append(_("Încă neapăsate: %s") % ", ".join(_(D.DUPA_ID[i][1]) for i in ramase))
	ev = S.ev
	if ev is not None and ev["dispozitiv"] != D.NATIV:
		randuri.append(_("de pe: %s, cod %d") % (ev["dispozitiv"], ev["cod"]))
	return {"titlu": _("Proba tastelor"), "mare": mare, "detalii": randuri, "istoric": []}


def _captura_asociere(D):
	a = S.asociere
	date = S.date
	t = D.gaseste(date, a.ident) if (a is not None and a.ident) else None
	if S.gata:
		asociate, sarite = a.rezumat()
		randuri = []
		if t is not None and t["fel"] == "usb":
			if D.opreste_neasociate(t):
				randuri.append(_("Tastele neasociate ale telecomenzii noi nu mai merg. În listă, ALBASTRU le lasă să treacă."))
			elif t.get("neasociate") == "opresc":
				randuri.append(_("Tastele neasociate se opresc numai după ce sunt asociate OK, săgețile, EXIT și MENU."))
			else:
				randuri.append(_("Tastele neasociate ale telecomenzii noi merg ca înainte."))
		randuri.append(_("Le probezi acum?"))
		return {"titlu": _("Asociază o telecomandă nouă"), "mare": _("Asociate %d, sărite %d.") % (asociate, sarite),
			"detalii": randuri, "istoric": [], "butoane": ["proba", "inchide"], "cerut": None}
	if a.stare == a.ALEGE:
		randuri = [_("O telecomandă USB (sau o tastatură) se bagă în receptor înainte; se vede imediat."),
			_("O telecomandă cu infraroșu, alta decât a receptorului, nu se poate asocia încă.")]
		if S.ir:
			randuri.append(_("Receptorul primește semnalul unei telecomenzi cu infraroșu, dar nu îl poate folosi încă."))
		if S.rezultat == "propriu":
			randuri.insert(0, _("Aceasta e telecomanda receptorului. Apasă un buton pe cealaltă telecomandă."))
		if S.asteapta:
			mare = (_("Am primit numai semnal infraroșu. Apasă OK ca să continui.") if S.ir
				else _("Nu am primit nimic de la telecomanda nouă. Apasă OK ca să continui."))
		else:
			mare = _("Apasă orice buton pe telecomanda nouă.")
		return {"titlu": _("Asociază o telecomandă nouă"), "mare": mare, "detalii": randuri, "istoric": [],
			"butoane": ["continua", "anuleaza"] if S.asteapta else ["anuleaza"], "cerut": None}
	b = a.buton_curent()
	randuri = []
	r = S.rezultat
	if r == "refacere" and t is not None:
		randuri.append(_("Telecomanda aceasta e deja asociată ca „%s”. O refaci buton cu buton.") % t["nume"])
	elif r in ("ales", "refacere") and t is not None:
		randuri.append(_("Telecomanda nouă: %s") % t["dispozitiv"])
	elif r == "asociat" and S.ultim is not None:
		bu, c = S.ultim
		randuri.append(_("%s = cod %d (0x%X)") % (_(bu[1]), c, c))
	elif r == "sarit" and S.ultim_sarit is not None:
		randuri.append(_("Sărit: %s") % _(S.ultim_sarit[1]))
	elif r == "alt_dispozitiv":
		randuri.append(_("Butonul a venit de pe alt dispozitiv; apasă pe telecomanda aleasă."))
	if a.confirma is not None:
		vechi = D.DUPA_COD.get(a.confirma[1])
		randuri.append(_("Codul acesta e deja folosit pentru %s. Apasă-l încă o dată ca să-l muți la %s, sau alt buton.") %
			(_(vechi[1]) if vechi else "?", _(b[1]) if b else "?"))
	if b is not None and b[0] == "power":
		randuri.append(_("Din standby adânc receptorul pornește numai cu telecomanda lui."))
	if a.de_baza_facute():
		randuri.append(_("Pe telecomanda nouă: ține apăsat 2 secunde = Sari; ține apăsat EXIT = Gata."))
	elif a.lipsa_pentru_gata():
		randuri.append(_("Pe telecomanda nouă: ține apăsat 2 secunde = Sari."))
		randuri.append(_("Gata cere și butoanele sărite: %s. Cu ROȘU (Înapoi) te întorci la ele.") %
			", ".join(_(D.DUPA_ID[i][1]) for i in a.lipsa_pentru_gata()))
	else:
		randuri.append(_("Pe telecomanda nouă: ține apăsat 2 secunde = Sari. Gata merge după MENU."))
	if S.asteapta:
		mare = _("Nu am primit nimic de la telecomanda nouă. Apasă OK ca să continui.")
	else:
		mare = _("Apasă pe telecomanda nouă butonul pentru: %s") % _(b[1]) if b is not None else ""
	butoane = ["continua"] if S.asteapta else ["inapoi", "sari"]
	if a.de_baza_facute() and not S.asteapta:
		butoane.append("gata")
	butoane.append("anuleaza")
	return {"titlu": _("Asociază o telecomandă nouă"), "mare": mare, "detalii": randuri,
		"istoric": [_("Asociate %d, sărite %d.") % (len(a.asociate), len(a.sarite))], "butoane": butoane,
		"cerut": b[0] if b is not None and not S.asteapta else None}


def stare():
	"""Pentru GET /api/telecomenzi. Prelucreaza tastele venite si da semnul de viata numai pentru captura paginii."""
	D = _d()
	m = _mapper()
	if m is not None and S.captura:
		if m.getCaptureMode() == m.captureOff:
			S.captura = False       # oprita fara semnal (de exemplu la oprirea interfetei)
		else:
			m.touch()
			_prelucreaza()
	if S.mod == MOD_CITITOR or (S.mod == MOD_ASOCIERE and S.asociere is not None and S.asociere.stare == S.asociere.ALEGE
			and S.captura):
		_citeste_ir()
	date, mesaj = _incarca(D) if S.date is None or S.mod != MOD_ASOCIERE else (S.date, "")
	captura = None
	if S.mod == MOD_CITITOR:
		captura = _captura_cititor(D)
	elif S.mod == MOD_PROBA and S.proba is not None:
		captura = _captura_proba(D)
	elif S.mod == MOD_ASOCIERE and S.asociere is not None:
		captura = _captura_asociere(D)
	if captura is not None:
		captura["secunde"] = _secunde(m)
		if S.mod in (MOD_CITITOR, MOD_PROBA):
			captura["iesire"] = S.oprita
	semne = []
	if S.mod == MOD_PROBA and S.proba is not None:
		semne = sorted(S.proba.verificate)
	elif S.mod == MOD_ASOCIERE and S.asociere is not None:
		semne = sorted(S.asociere.asociate)
	return {
		"result": True,
		"disponibil": m is not None,
		"mod": S.mod,
		"captura_pagina": bool(S.captura),
		"captura_televizor": bool(_captura_televizor(m)),
		"captura": captura,
		"aprinse": sorted(S.aprinse),
		"semne": semne,
		"proba_inceputa": bool(S.proba is not None and S.proba.verificate),
		"proba_text": (_("%d din %d de butoane verificate") % (len(S.proba.verificate), D.NUMAR_BUTOANE)
			if S.proba is not None and S.proba.verificate else ""),
		"telecomenzi": _telecomenzi(D, date),
		"mesaj_fisier": mesaj,
		"butoane_viper": [{"id": b[0], "eticheta": _(b[1]), "cod": b[2]} for b in D.BUTOANE_VIPER],
	}


# ------------------------------------------------------------------ rutele
def argumente(request):
	permise = ("fel", "pas", "pastreaza", "actiune", "id", "cod", "nume", "confirmat", "format")
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:12]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:64].strip()
	return rez


def _scoateCod(corp):
	cod = corp.pop("_cod", 200)
	return corp, cod


def rute(baza, resource):
	"""({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def lucru(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				corp, cod = _scoateCod(self.lucru(argumente(request)))
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				_jurnal("eroare: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class CapturaResource(_Schimba):
		def lucru(self, a):
			return porneste(a.get("fel", ""))

	class AsociereResource(_Schimba):
		def lucru(self, a):
			return pas(a.get("pas", ""), a.get("pastreaza"))

	class SchimbaResource(_Schimba):
		def lucru(self, a):
			return schimba(a.get("actiune", ""), a.get("id", ""), a.get("cod", ""), a.get("nume", ""), a.get("confirmat", ""))

	class ExportResource(baza):
		"""GET /api/telecomenzi-export?format=json|csv: fisier de salvat (codurile pentru aplicatii)."""

		def render_GET(self, request):
			D = _d()
			fel = argumente(request).get("format", "json")
			if fel not in ("json", "csv"):
				return self._eroare(request, _t("Se alege format=json sau format=csv."))
			date, _mesaj = _incarca(D)
			if fel == "json":
				corp, tip = D.export_json(date), b"application/json; charset=utf-8"
			else:
				corp, tip = D.export_csv(date), b"text/csv; charset=utf-8"
			request.setResponseCode(200)
			request.setHeader(b"content-type", tip)
			request.setHeader(b"cache-control", b"no-store")
			request.setHeader(b"content-disposition", ("attachment; filename=telecomenzi.%s" % fel).encode("ascii"))
			return corp.encode("utf-8", "replace")

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"telecomenzi": StareResource(),
		b"telecomenzi-captura": CapturaResource(),
		b"telecomenzi-asociere": AsociereResource(),
		b"telecomenzi-schimba": SchimbaResource(),
		b"telecomenzi-export": ExportResource(),
	}
	return api, PaginaResource()


# ------------------------------------------------------------------ pagina
def _desen():
	"""Desenul SVG al telecomenzii (fisierul imaginii, al nostru); '' daca lipseste sau nu e SVG."""
	cale = CALE_DESEN_SVG
	if cale is None:
		try:
			from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
			cale = resolveFilename(SCOPE_SKIN_IMAGE, "telecomanda-viper.svg")
		except Exception:
			cale = "/usr/share/enigma2/telecomanda-viper.svg"
	try:
		with open(cale, "rb") as f:
			text = f.read(256 * 1024).decode("utf-8", "replace")
	except (OSError, IOError):
		return ""
	inceput = text.find("<svg")
	if inceput < 0 or "<script" in text.lower() or "onload" in text.lower():
		return ""
	return text[inceput:]


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


def pagina_text(stil, config_pagina, desen=None):
	svg = _desen() if desen is None else desen
	if not svg:
		# pus dupa traducerea paginii, deci tradus aici
		svg = "<p class=\"nota\">%s</p>" % _t("Desenul telecomenzii lipsește din imagine.").replace("&", "&amp;").replace(
			"<", "&lt;")
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__DESEN__", svg).replace("__CONFIG__",
		config_pagina).replace(
		"__DRUM_MENIU__", _drumMeniu("hds_telecomenzi"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telecomenzi</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .grila{display:grid;grid-template-columns:minmax(150px,230px) 1fr;gap:16px;align-items:start;}
  .desen svg{width:100%;height:auto;display:block;}
  .desen g.buton{cursor:pointer;}
  .desen g.buton:hover polygon:not(.pictograma),.desen g.buton:hover circle:not(.pictograma){stroke:#9fb4d6;stroke-width:2;}
  .desen g.aprins polygon:not(.pictograma),.desen g.aprins circle:not(.pictograma){fill:#ffb23c;}
  .desen g.semn polygon:not(.pictograma),.desen g.semn circle:not(.pictograma){stroke:#35d07a;stroke-width:3;}
  .desen g.cerut polygon:not(.pictograma),.desen g.cerut circle:not(.pictograma){animation:puls 1s infinite;}
  @keyframes puls{0%,100%{fill:#ffb23c;}50%{fill:#6b4a12;}}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .mare{font-size:1.6rem;color:#ffd27a;margin:0 0 10px;line-height:1.25;word-break:break-word;}
  .randuri p{margin:4px 0;line-height:1.4;font-size:.95rem;}
  .istoric{font-family:monospace;font-size:.78rem;line-height:1.4;white-space:pre-wrap;word-break:break-word;color:var(--text-slab);margin:8px 0 0;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.rosu{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.galben{background:var(--galben);border-color:var(--galben);color:#241d00;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  .tel{border-top:1px solid var(--bordura);padding:10px 0;}
  .tel:first-child{border-top:0;}
  .tel .nume{font-size:1rem;margin:0 0 6px;}
  .tel.oprita .nume{color:var(--text-slab);}
  .tel details{margin-top:8px;}
  .tel li{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:4px 0;font-size:.9rem;}
  .tel ul{list-style:none;padding:0;margin:6px 0 0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:640px){ .grila{grid-template-columns:1fr;} .desen{max-width:200px;margin:0 auto;} }
</style>
</head>
<body>
<main>
<h1>Telecomenzi</h1>
<p class="mesaj" id="incarcare">Se citesc telecomenzile...</p>
<div id="continut" class="ascuns">
<div class="grila">
  <div>
    <div class="desen" id="desen">__DESEN__</div>
    <p class="nota">Apasă un buton pe desen: receptorul îl primește ca de pe telecomanda lui. Ținut apăsat = apăsare lungă.</p>
  </div>
  <div>
    <section class="card" id="cardCaptura">
      <h2 id="titluCaptura">Utilitare</h2>
      <div id="captura" class="ascuns">
        <p class="mare" id="mare"></p>
        <div class="randuri" id="detalii"></div>
        <pre class="istoric" id="istoric"></pre>
        <p class="nota" id="secunde"></p>
      </div>
      <div class="butoane" id="butoaneCaptura"></div>
      <p class="nota" id="notaTelevizor"></p>
    </section>
    <section class="card">
      <h2>Telecomenzile asociate</h2>
      <div id="lista"></div>
      <p class="nota" id="fisier"></p>
      <div class="butoane">
        <button type="button" class="rosu" id="stergeTot">Șterge toate asocierile</button>
        <a href="#" id="exportJson">Export JSON</a>
        <a href="#" id="exportCsv">Export CSV</a>
      </div>
    </section>
    <p class="mesaj" id="mesaj"></p>
    <p class="nota">Același utilitar e pe televizor, în __DRUM_MENIU__. Cât ascultă pagina, tastele merg și pe televizor, cel mult 2 minute, iar pe televizor apare un anunț. Din standby adânc receptorul pornește numai cu telecomanda lui.</p>
  </div>
</div>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var CEAS = null;
function $(id){ return document.getElementById(id); }
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
function buton(text, clasa, f){ var b = document.createElement("button"); b.type = "button"; b.textContent = text; if(clasa){ b.className = clasa; } b.addEventListener("click", f); return b; }
function post(cale, valori){
  var q = new URLSearchParams(); Object.keys(valori || {}).forEach(function(k){ q.set(k, valori[k]); });
  return cerere(cale, "POST", q).then(function(d){
    if(d.intrebare === "pastreaza"){
      var pastreaza = confirm(d.message + " (OK = da, Anulează = nu)");
      return post("/api/telecomenzi-asociere", {pas: "anuleaza", pastreaza: pastreaza ? "1" : "0"});
    }
    if(d.intrebare === "sterge" || d.intrebare === "sterge-tot"){
      if(!confirm(d.message)){ return d; }
      valori.confirmat = "1";
      return post(cale, valori);
    }
    mesaj(d.message, !d.result);
    if(d.telecomenzi){ arata(d); }
    return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function clasa(ids, nume){
  document.querySelectorAll("#desen g." + nume).forEach(function(g){ g.classList.remove(nume); });
  (ids || []).forEach(function(i){ var g = document.getElementById("b-" + i); if(g){ g.classList.add(nume); } });
}
var TEXT_BUTOANE = {inapoi: ["Înapoi", "rosu"], sari: ["Sari", "galben"], gata: ["Gata", "verde"], anuleaza: ["Anulează", ""], continua: ["Continuă", "verde"], proba: ["Le probez acum", "verde"], inchide: ["Închide", ""]};
function arataCaptura(d){
  var c = d.captura, b = $("butoaneCaptura"); b.textContent = "";
  $("notaTelevizor").textContent = d.captura_televizor ? "Ecranul Telecomenzi e deschis pe televizor." : "";
  if(!d.disponibil){ $("notaTelevizor").textContent = "Receptorul nu are utilitarul telecomenzilor."; }
  if(!c){
    $("titluCaptura").textContent = "Utilitare";
    $("captura").classList.add("ascuns");
    b.appendChild(buton("Cititor de coduri", "", function(){ post("/api/telecomenzi-captura", {fel: "cititor"}); }));
    b.appendChild(buton(d.proba_inceputa ? "Proba tastelor: " + d.proba_text : "Proba tastelor", "", function(){ post("/api/telecomenzi-captura", {fel: "proba"}); }));
    if(d.proba_inceputa){ b.appendChild(buton("Începe din nou", "", function(){ post("/api/telecomenzi-captura", {fel: "proba-noua"}); })); }
    b.appendChild(buton("Asociază o telecomandă nouă", "verde", function(){ post("/api/telecomenzi-captura", {fel: "asociere"}); }));
    clasa([], "cerut");
    return;
  }
  $("titluCaptura").textContent = c.titlu;
  $("captura").classList.remove("ascuns");
  $("mare").textContent = c.mare || "";
  var det = $("detalii"); det.textContent = "";
  (c.detalii || []).forEach(function(t){ var p = document.createElement("p"); p.textContent = t; det.appendChild(p); });
  $("istoric").textContent = (c.istoric || []).join("\\n");
  $("secunde").textContent = [c.secunde || "", c.iesire || ""].join(" ").trim();
  if(d.mod === "asociere"){
    (c.butoane || []).forEach(function(n){
      var t = TEXT_BUTOANE[n];
      b.appendChild(buton(t[0], t[1], function(){ post("/api/telecomenzi-asociere", {pas: n}); }));
    });
    clasa(c.cerut ? [c.cerut] : [], "cerut");
  } else {
    if(d.captura_pagina){ b.appendChild(buton("Oprește", "rosu", function(){ post("/api/telecomenzi-captura", {fel: "oprit"}); })); }
    else {
      b.appendChild(buton("Pornește din nou", "verde", function(){ post("/api/telecomenzi-captura", {fel: d.mod}); }));
      b.appendChild(buton("Închide", "", function(){ post("/api/telecomenzi-captura", {fel: "oprit"}); }));
    }
    clasa([], "cerut");
  }
}
function arataLista(d){
  var l = $("lista"); l.textContent = "";
  if(!d.telecomenzi.length){ var p = document.createElement("p"); p.className = "nota"; p.textContent = "Nicio telecomandă asociată."; l.appendChild(p); }
  d.telecomenzi.forEach(function(t){
    var div = document.createElement("div"); div.className = "tel" + (t.activa ? "" : " oprita");
    var n = document.createElement("p"); n.className = "nume"; n.textContent = t.text; div.appendChild(n);
    if(t.dispozitiv){ var dv = document.createElement("p"); dv.className = "nota"; dv.textContent = "Dispozitiv: " + t.dispozitiv; div.appendChild(dv); }
    if(t.nota){ var no = document.createElement("p"); no.className = "nota"; no.textContent = t.nota; div.appendChild(no); }
    var bb = document.createElement("div"); bb.className = "butoane";
    bb.appendChild(buton("Șterge telecomanda", "rosu", function(){ post("/api/telecomenzi-schimba", {actiune: "sterge", id: t.id}); }));
    bb.appendChild(buton(t.activa ? "Oprește" : "Pornește", "verde", function(){ post("/api/telecomenzi-schimba", {actiune: "activa", id: t.id}); }));
    bb.appendChild(buton("Redenumește", "galben", function(){
      var nume = prompt("Numele telecomenzii", t.nume);
      if(nume && nume.trim()){ post("/api/telecomenzi-schimba", {actiune: "redenumeste", id: t.id, nume: nume.trim()}); }
    }));
    if(t.text_neasociate){ bb.appendChild(buton(t.text_neasociate, "albastru", function(){ post("/api/telecomenzi-schimba", {actiune: "neasociate", id: t.id}); })); }
    div.appendChild(bb);
    var det = document.createElement("details");
    var s = document.createElement("summary"); s.textContent = "Tastele asociate"; det.appendChild(s);
    det.addEventListener("toggle", function(){ clasa(det.open ? t.semne : (d.semne || []), "semn"); });
    var ul = document.createElement("ul");
    if(!t.taste.length){ var li0 = document.createElement("li"); li0.textContent = "Nicio tastă asociată."; ul.appendChild(li0); }
    t.taste.forEach(function(k){
      var li = document.createElement("li"); var sp = document.createElement("span"); sp.textContent = k.text; li.appendChild(sp);
      li.appendChild(buton("Șterge asocierea tastei", "", function(){ post("/api/telecomenzi-schimba", {actiune: "sterge-tasta", id: t.id, cod: String(k.cod)}); }));
      ul.appendChild(li);
    });
    det.appendChild(ul); div.appendChild(det); l.appendChild(div);
  });
  $("stergeTot").classList.toggle("ascuns", !d.telecomenzi.length);
  $("fisier").textContent = d.mesaj_fisier || "";
}
function arata(d){
  DATE = d;
  arataCaptura(d);
  arataLista(d);
  clasa(d.aprinse, "aprins");
  clasa(d.semne, "semn");
  planifica(d.captura_pagina ? 1000 : 5000);
}
function citeste(){
  cerere("/api/telecomenzi").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi telecomenzile."; planifica(5000); return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; planifica(5000); });
}
function planifica(ms){ if(CEAS){ clearTimeout(CEAS); } CEAS = setTimeout(citeste, ms); }
function tasta(cod, lung){
  var q = new URLSearchParams(); q.set("command", String(cod)); if(lung){ q.set("lung", "1"); }
  cerere("/api/remotecontrol", "POST", q).then(function(d){ if(!d.result){ mesaj(d.message, true); } }).catch(function(){ mesaj("Tasta nu a ajuns la receptor.", true); });
}
(function(){
  var tinut = null, lung = false;
  document.querySelectorAll("#desen g.buton").forEach(function(g){
    var cod = parseInt(g.getAttribute("data-cod"), 10);
    g.addEventListener("pointerdown", function(e){ e.preventDefault(); lung = false; tinut = setTimeout(function(){ lung = true; tasta(cod, true); }, 700); });
    g.addEventListener("pointerup", function(){ if(tinut){ clearTimeout(tinut); tinut = null; } if(!lung){ tasta(cod, false); } });
    g.addEventListener("pointerleave", function(){ if(tinut){ clearTimeout(tinut); tinut = null; } });
  });
})();
$("stergeTot").addEventListener("click", function(){ post("/api/telecomenzi-schimba", {actiune: "sterge-tot"}); });
$("exportJson").href = adresa("/api/telecomenzi-export?format=json");
$("exportCsv").href = adresa("/api/telecomenzi-export?format=csv");
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
		N_("Telecomenzi"),
		N_("Se citesc telecomenzile..."),
		N_("Apasă un buton pe desen: receptorul îl primește ca de pe telecomanda lui. Ținut apăsat = "
			"apăsare lungă."),
		N_("Utilitare"),
		N_("Telecomenzile asociate"),
		N_("Șterge toate asocierile"),
		N_("Export JSON"),
		N_("Export CSV"),
		N_("Același utilitar e pe televizor, în __DRUM_MENIU__. Cât ascultă pagina, tastele merg și pe "
			"televizor, cel mult 2 minute, iar pe televizor apare un anunț. Din standby adânc receptorul "
			"pornește numai cu telecomanda lui."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("(OK = da, Anulează = nu)"),
		N_("Receptorul nu răspunde."),
		N_("Înapoi"),
		N_("Sari"),
		N_("Gata"),
		N_("Anulează"),
		N_("Continuă"),
		N_("Le probez acum"),
		N_("Închide"),
		N_("Ecranul Telecomenzi e deschis pe televizor."),
		N_("Receptorul nu are utilitarul telecomenzilor."),
		N_("Utilitare"),
		N_("Cititor de coduri"),
		N_("Proba tastelor:"),
		N_("Proba tastelor"),
		N_("Începe din nou"),
		N_("Asociază o telecomandă nouă"),
		N_("Oprește"),
		N_("Pornește din nou"),
		N_("Nicio telecomandă asociată."),
		N_("Dispozitiv:"),
		N_("Șterge telecomanda"),
		N_("Pornește"),
		N_("Redenumește"),
		N_("Numele telecomenzii"),
		N_("Tastele asociate"),
		N_("Nicio tastă asociată."),
		N_("Șterge asocierea tastei"),
		N_("Receptorul nu a putut citi telecomenzile."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Tasta nu a ajuns la receptor."),
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
