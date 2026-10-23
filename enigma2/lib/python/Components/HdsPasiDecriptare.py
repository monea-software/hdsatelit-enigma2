# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPasiDecriptare.py: pasii decriptarii canalului de pe televizor, ca jurnal viu scurt, cu ora socotita de la
# pornirea canalului: cererea catre modulul de acces (sistemele si CAID-urile din PMT), raspunsurile modulului si timpul
# lor, lipsa raspunsului, imaginea decriptata sau oprita (din decodor), starea si mesajele modulelor CI. Se vede pe
# televizor sub mesajul canalului criptat (Screens/HdsEcranNegru.py), in interfata web in pagina TV (player.js) si la
# randul Acces din panou (HdsWebControl/pasi_decriptare_web.py, GET /api/pasi-decriptare), din aceleasi functii.
#
# GENERAL, PENTRU ORICE MODUL DE ACCES (software sau CI). Nimic din acest fisier nu e al unui modul anume:
# - cererea: enigma2 trimite oricarui modul software, la PMT gata, CAID-urile si PID-urile ECM ale canalului (CA PMT,
#   lib/dvb/pmt.cpp, eDVBCAService), pe soclul SOCKET pe care asculta modulul (enigma2 e clientul); modulele CI primesc
#   canalul prin slotul lor. Din Python se vad aceleasi CAID-uri si PID-uri ECM (sCAIDPIDs, apoi sCAIDs) si ora la care
#   s-au aflat; soclul care exista spune ca un modul software asculta, sloturile CI gata si potrivite canalului (regula
#   lui enigma2, HdsCommon.ci_slot_matches) spun ca cererea trece prin modulul CI;
# - raspunsul: fisierul de stare pe care il scriu de obicei modulele software dupa fiecare raspuns, desfacut generic de
#   Components/HdsEcm.py (HdsCommon.ecm_info). De aici se folosesc NUMAI CAID-ul, PID-ul ECM, timpul raspunsului si ora
#   fisierului; un camp care lipseste nu se arata. Cititoarele, adresele, porturile, protocoalele si pasii prin retea nu
#   se citesc aici si nu ajung nicaieri; continutul fisierului nu se scrie in jurnalele receptorului. Un raspuns conteaza
#   numai daca e scris dupa pornirea canalului, e pentru un CAID al canalului si, cand PMT-ul da PID-urile ECM ale
#   CAID-ului, pentru unul dintre ele (aceeasi regula ca HdsCommon.ecm_active);
# - decodorul: imaginea vine sau nu (Components/HdsEcranNegru.Urmaritor.imagine: contorul de cadre al decodorului sau
#   evenimentul de marime video);
# - modulele CI: starea slotului (fara modul, porneste, gata) si mesajele MMI ale modulului. Mesajele le citeste numai
#   Screens/Ci.py (MMIDialog.showScreen), fiindca enigma2 le da o singura data (getMMIScreen); de acolo vin la mesaj_ci().
#
# CINE CHEAMA: Components/HdsEcranNegru.Urmaritor, care oricum urmareste canalul redat (o data pe secunda cat se asteapta
# imaginea, o data la doua secunde cand vine), cheama noteaza_din() numai cu setarea pornita; ruta web si pagina TV
# citesc doar ce s-a notat (date_web), fara alta citire.
#
# SETAREA: config.usage.hds_pasi_decriptare (setup.xml la usage, langa explicatiile de pe ecranul negru, deci si in
# pagina web de setari si in Cauta setari), oprita din fabrica. Oprita: nicio citire in plus, nimic nou pe televizor,
# iar ruta web raspunde cu o lista goala.
#
# Partea de sus nu importa nimic din enigma2: probele de pe PC dau fotografiile, ceasul si modulul HdsCommon.

import os
import time

SOCKET = "/tmp/camd.socket"     # soclul pe care asculta un modul software (lib/dvb/pmt.cpp se leaga aici)
MAX_EVENIMENTE = 40             # cat tine minte jurnalul unui canal (primul rand, cererea, ramane mereu)
RANDURI_TV = 5                  # cate randuri se vad pe televizor (Screens/HdsEcranNegru.py, PASI_RANDURI)
RANDURI_WEB = 12                # cate randuri da ruta web
SISTEME_CERERE = 2              # cate CAID-uri se numesc in randul cererii (cele cu acelasi nume de sistem intr-un
                                # singur grup: "NDS VideoGuard (CAID 098C, 098D)"); restul: si inca N
PRAG_FARA_RASPUNS_S = 3         # dupa atatea secunde fara raspuns scris, randul viu "nu a scris niciun raspuns"
FARA_RASPUNS_MAX_S = 999
MESAJ_CI_MAX = 100
MESAJ_CI_DUBLU_S = 5.0          # acelasi mesaj CI repetat in atat timp nu se scrie a doua oara

# felurile evenimentelor
CERERE = "cerere"
CERERE_CI = "cerere_ci"
FARA_MODUL = "fara_modul"
RASPUNS = "raspuns"
FARA_RASPUNS = "fara_raspuns"
IMAGINE = "imagine"
IMAGINE_OPRITA = "imagine_oprita"
IMAGINE_DIN_NOU = "imagine_din_nou"
CI_GATA = "ci_gata"
CI_PORNESTE = "ci_porneste"
CI_SCOS = "ci_scos"
CI_MESAJ = "ci_mesaj"


def N_(text):
	"""Marcaj pentru xgettext, fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# ---------------------------------------------------------------- textele

T_CERERE = N_("Cerere către modulul de acces: %s")
T_CERERE_CI = N_("Cerere către modulul CI %(modul)s: %(sisteme)s")
T_FARA_MODUL = N_("Niciun modul de acces nu ascultă, deci cererea nu pleacă: %s")
T_RASPUNS_MS = N_("Răspuns de la modulul de acces pentru %(sistem)s în %(ms)d ms")
T_RASPUNS = N_("Răspuns de la modulul de acces pentru %s")
T_FARA_RASPUNS = N_("Modulul de acces nu a scris niciun răspuns de %d s")
T_IMAGINE = N_("Imaginea s-a decriptat.")
T_IMAGINE_OPRITA = N_("Imaginea s-a oprit.")
T_IMAGINE_DIN_NOU = N_("Imaginea a pornit din nou.")
T_CI_GATA = N_("Modulul CI %s este gata.")
T_CI_PORNESTE = N_("Modulul CI din slotul %d pornește.")
T_CI_SCOS = N_("Modulul CI din slotul %d a fost scos.")
T_CI_MESAJ = N_("Modulul CI spune: %s")
T_SI_INCA = N_("și încă %d")
# randul din setup.xml (aceleasi texte acolo; aici numai pentru xgettext si probe)
T_SETARE = N_("Arată pașii decriptării")
T_SETARE_DESCRIERE = N_("Da: la canalele criptate, sub mesajul de pe ecranul negru și în interfața web apar pașii decriptării pe măsură ce se întâmplă: cererea către modulul de acces, răspunsurile și timpul lor, imaginea decriptată, mesajele modulului CI. Nu: nimic din toate acestea.")


# ---------------------------------------------------------------- setarea

def initConfig():
	"""config.usage.hds_pasi_decriptare, oprita din fabrica. Se poate chema de mai multe ori."""
	try:
		from Components.config import config, ConfigYesNo
		try:
			config.usage.hds_pasi_decriptare
		except (KeyError, AttributeError):
			# ConfigSubsection da KeyError (nu AttributeError) pentru o cheie care lipseste
			config.usage.hds_pasi_decriptare = ConfigYesNo(default=False)
	except Exception as e:
		print("[HdsPasiDecriptare] setarea: %s" % e)


def pornit():
	"""True numai cu setarea pornita; fara setare (alt fisier de configurare, probe): False."""
	try:
		from Components.config import config
		return bool(config.usage.hds_pasi_decriptare.value)
	except Exception:
		return False


# ---------------------------------------------------------------- ajutoare

def _monoton():
	try:
		return time.monotonic()
	except AttributeError:
		return time.time()


def _c(C=None):
	if C is not None:
		return C
	try:
		from Components.Converter import HdsCommon
		return HdsCommon
	except Exception:
		return None


def _curat(text, n=120):
	"""Text venit din afara (numele modulului CI, mesajul lui): fara caractere de control, fara spatii in plus, taiat."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return u""
	t = u"".join(c if (c >= u" " and c != u"\x7f") else u" " for c in t)
	return u" ".join(t.split())[:n]


def _int(v, implicit=-1):
	try:
		return int(v)
	except (TypeError, ValueError):
		return implicit


def _secunde(x, C=None):
	"""1.4 -> "1,4" (separatorul zecimal al limbii, HdsCommon.fmt_dec), cu rezerva cu virgula pe PC."""
	C = _c(C)
	try:
		if C is not None:
			s = C.fmt_dec(x, 1)
			if s:
				return s
	except Exception:
		pass
	return (u"%.1f" % float(x)).replace(u".", u",")


def _nume_sistem(caid, C=None):
	"""Numele sistemului din tabelul skinului (HdsCommon.caid_name), "" cand nu e in tabel."""
	C = _c(C)
	try:
		return (C.caid_name(caid) or u"") if C is not None else u""
	except Exception:
		return u""


def _grup(nume, caids):
	"""NDS VideoGuard (CAID 098C, 098D); fara nume: CAID 0500."""
	coduri = u", ".join(u"%04X" % (c & 0xFFFF) for c in caids)
	return (u"%s (CAID %s)" % (nume, coduri)) if nume else (u"CAID %s" % coduri)


def _sistem(caid, C=None):
	"""Viaccess (CAID 0500); fara nume in tabelul skinului: CAID 0500."""
	caid = _int(caid) & 0xFFFF
	return _grup(_nume_sistem(caid, C), [caid])


def _sisteme(lista, C=None):
	"""Primele SISTEME_CERERE CAID-uri din lista [(caid, pid)], in ordinea PMT-ului, apoi si inca N. CAID-urile numite
	cu acelasi sistem stau intr-un singur grup, cu numele o data: "NDS VideoGuard (CAID 098C, 098D) si inca 1", nu
	"NDS VideoGuard (CAID 098C), NDS VideoGuard (CAID 098D) si inca 1" (randul de pe televizor e mai scurt)."""
	caids = []
	for caid, _pid in lista:
		caid = _int(caid)
		if caid > 0 and caid not in caids:
			caids.append(caid)
	grupuri = []
	for caid in caids[:SISTEME_CERERE]:
		nume = _nume_sistem(caid & 0xFFFF, C)
		for g in grupuri:
			if nume and g[0] == nume:
				g[1].append(caid)
				break
		else:
			grupuri.append((nume, [caid]))
	text = u", ".join(_grup(nume, c) for nume, c in grupuri)
	rest = len(caids) - SISTEME_CERERE
	if rest > 0:
		text = text + u" " + _t(T_SI_INCA) % rest
	return text


# ---------------------------------------------------------------- jurnalul unui canal

class Jurnal(object):
	"""Pasii decriptarii unui canal redat, de la pornirea lui (t0, ceasul monoton; t0_perete, ceasul obisnuit, pentru
	ora fisierului de stare). Evenimentele: [secunde de la pornire, fel, parametri]."""

	def __init__(self, ref, t0, t0_perete):
		self.ref = ref or u""
		self.t0 = t0
		self.t0_perete = t0_perete
		self.ev = []
		self.criptat = None
		self.cerere = None         # CAID-urile din cerere (tuple), None cat nu s-a trimis
		self.t_cerere = None
		self.modul = None          # "soft", "ci" sau "" (niciun modul) la cerere
		self.ecm_mtime = None      # ora fisierului de stare vazuta ultima data
		self.raspunsuri = 0
		self.fara = None           # randul viu "nu a scris niciun raspuns"
		self.img = None            # imaginea, cum s-a vazut ultima data pe canalul criptat
		self.decriptat = False     # imaginea a venit macar o data
		self.ci = {}               # slot -> starea vazuta ultima data
		self.ci_ultim = (None, -1000.0)

	def _adauga(self, t, fel, **p):
		e = [max(0.0, float(t)), fel, p]
		self.ev.append(e)
		if len(self.ev) > MAX_EVENIMENTE:
			# primul rand (de obicei cererea) ramane; pleaca cel mai vechi de dupa el
			del self.ev[1]
		return e

	def noteaza(self, f, acum, perete):
		"""O fotografie a canalului (vezi noteaza_din): ce s-a schimbat de la cea dinainte devine eveniment."""
		rel = max(0.0, acum - self.t0)
		criptat = f.get("criptat")
		if criptat is not True:
			# canal liber sau inca nestiut (fara PMT): nimic de aratat
			if self.criptat is not True:
				self.criptat = criptat
			return
		self.criptat = True
		caidpids = [(c, p) for c, p in (f.get("caidpids") or []) if _int(c) > 0]
		caids = [c for c in (f.get("caids") or []) if _int(c) > 0]
		canal = set(c for c, _p in caidpids) | set(caids)
		# 1. cererea: o data, cand PMT-ul s-a citit si canalul are CAID-uri
		if self.cerere is None and f.get("pmt") and canal:
			lista = caidpids or [(c, -1) for c in caids]
			self.cerere = tuple(c for c, _p in lista)
			self.t_cerere = rel
			modul = f.get("modul") or ("", -1, u"")
			self.modul = modul[0]
			if modul[0] == "ci":
				self._adauga(rel, CERERE_CI, lista=lista, modul=_curat(modul[2], 40))
			elif modul[0] == "soft":
				self._adauga(rel, CERERE, lista=lista)
			else:
				self._adauga(rel, FARA_MODUL, lista=lista)
		# 2. raspunsul modulului, din fisierul de stare (numai CAID, PID, timp, ora)
		e = f.get("ecm") or {}
		mt = e.get("mtime")
		if mt is not None and mt != self.ecm_mtime:
			prima = self.ecm_mtime is None
			self.ecm_mtime = mt
			ceas_bun = self.t0_perete <= perete + 5.0
			# prima vedere: numai un raspuns scris dupa pornire (ceasul dat inapoi: nimic sigur, deci nimic); o schimbare
			# vazuta dupa pornire e un raspuns nou, scris acum
			nou = (not prima) or (ceas_bun and mt >= self.t0_perete - 1.0)
			caid = _int(e.get("caid"))
			pid = _int(e.get("pid"), 0)
			pids = [p for c, p in caidpids if c == caid and 0 < p < 0x1FFF]
			if nou and caid > 0 and caid in canal and not (pid > 0 and pids and pid not in pids):
				# ora raspunsului din ora fisierului, cand ceasurile se potrivesc; altfel ora la care s-a vazut
				t = (mt - self.t0_perete) if ceas_bun else rel
				if not -1.0 <= t <= rel + 1.0:
					t = rel
				ms = _int(e.get("ms"))
				self._adauga(max(0.0, min(rel, t)), RASPUNS, caid=caid, ms=ms if 0 <= ms < 600000 else -1)
				self.raspunsuri += 1
				self.fara = None
		# 3. lipsa raspunsului (numai la un modul software: modulele CI nu scriu fisierul de stare)
		if self.cerere is not None and self.modul == "soft" and self.raspunsuri == 0 and not self.decriptat:
			s = int(rel - self.t_cerere)
			if s >= PRAG_FARA_RASPUNS_S:
				s = min(s, FARA_RASPUNS_MAX_S)
				if self.fara is None:
					self.fara = self._adauga(self.t_cerere + PRAG_FARA_RASPUNS_S, FARA_RASPUNS, s=s)
				else:
					self.fara[2]["s"] = s
		# 4. imaginea, din decodor
		img = f.get("imagine")
		if img is True and self.img is not True:
			self._adauga(rel, IMAGINE_DIN_NOU if self.decriptat else IMAGINE)
			self.decriptat = True
			self.fara = None
		elif img is False and self.img is True:
			self._adauga(rel, IMAGINE_OPRITA)
		if img is not None:
			self.img = img
		# 5. starea sloturilor CI (numai schimbarile de dupa pornire)
		for slot, stare, nume in f.get("ci") or []:
			vechi = self.ci.get(slot)
			self.ci[slot] = stare
			if vechi is None or vechi == stare:
				continue
			if stare == 2:
				self._adauga(rel, CI_GATA, modul=_curat(nume, 40) or (u"%d" % (slot + 1)))
			elif stare == 1:
				self._adauga(rel, CI_PORNESTE, slot=slot + 1)
			elif stare == 0:
				self._adauga(rel, CI_SCOS, slot=slot + 1)

	def mesaj_ci(self, text, acum):
		text = _curat(text, MESAJ_CI_MAX)
		if not text:
			return
		vechi, cand = self.ci_ultim
		if vechi == text and acum - cand < MESAJ_CI_DUBLU_S:
			return
		self.ci_ultim = (text, acum)
		self._adauga(max(0.0, acum - self.t0), CI_MESAJ, text=text)

	# ---- textele

	def text(self, e, C=None):
		t, fel, p = e
		if fel == CERERE:
			return _t(T_CERERE) % _sisteme(p["lista"], C)
		if fel == CERERE_CI:
			return _t(T_CERERE_CI) % {"modul": p.get("modul") or u"", "sisteme": _sisteme(p["lista"], C)}
		if fel == FARA_MODUL:
			return _t(T_FARA_MODUL) % _sisteme(p["lista"], C)
		if fel == RASPUNS:
			sistem = _sistem(p["caid"], C)
			if p.get("ms", -1) >= 0:
				return _t(T_RASPUNS_MS) % {"sistem": sistem, "ms": p["ms"]}
			return _t(T_RASPUNS) % sistem
		if fel == FARA_RASPUNS:
			return _t(T_FARA_RASPUNS) % p["s"]
		if fel == IMAGINE:
			return _t(T_IMAGINE)
		if fel == IMAGINE_OPRITA:
			return _t(T_IMAGINE_OPRITA)
		if fel == IMAGINE_DIN_NOU:
			return _t(T_IMAGINE_DIN_NOU)
		if fel == CI_GATA:
			return _t(T_CI_GATA) % p["modul"]
		if fel == CI_PORNESTE:
			return _t(T_CI_PORNESTE) % p["slot"]
		if fel == CI_SCOS:
			return _t(T_CI_SCOS) % p["slot"]
		if fel == CI_MESAJ:
			return _t(T_CI_MESAJ) % p["text"]
		return u""

	def alese(self, n):
		"""Cel mult n evenimente: primul (cererea) si ultimele n - 1."""
		if n <= 0 or self.criptat is not True:
			return []
		if len(self.ev) <= n:
			return list(self.ev)
		return [self.ev[0]] + self.ev[-(n - 1):] if n > 1 else self.ev[-1:]

	def randuri(self, n=RANDURI_TV, C=None):
		"""Randurile pentru televizor: "+0,4 s   Cerere catre modulul de acces: ..."."""
		return [u"+%s s   %s" % (_secunde(e[0], C), self.text(e, C)) for e in self.alese(n)]

	def web(self, n=RANDURI_WEB, C=None):
		return [{"t": u"+%s s" % _secunde(e[0], C), "text": self.text(e, C), "fel": e[1]} for e in self.alese(n)]


# ---------------------------------------------------------------- randurile in caseta de pe televizor
#
# Pasii sunt o singura eticheta cu mai multe randuri ("\n"), deci derularea randurilor care nu incap (lib/gui/elabel,
# numai pentru etichetele de un rand) nu o atinge, iar eticheta (noWrap) taia randul lung la marginea casetei, in
# mijlocul cuvantului. Aici un rand mai lat decat caseta se rupe intre cuvinte pe randul urmator, cu continuarea
# aliniata dupa timp; fontul ramane cel ales (si cu textul marit), niciun cuvant nu se taie. Masura o da eticheta
# insasi (Screens/HdsEcranNegru.py): cu noWrap, calculateSize da latimea intreaga a unui rand.

SEPARATOR = u"   "              # intre timp si text, ca in Jurnal.randuri
MEMORIE_MAX = 100               # cate randuri rupte tine minte fereastra (randul viu se schimba in fiecare secunda)


def _indent(cap, masoara):
	"""Spatiile cat latimea timpului cu separatorul ("+1,5 s   "), masurate cu acelasi font; "" cand nu se poate."""
	if not cap:
		return u""
	spatiu = (masoara(u"x" + u" " * 10 + u"x") - masoara(u"xx")) / 10.0
	latime = masoara(cap + u"x") - masoara(u"x")
	if spatiu <= 0 or latime <= 0:
		return u""
	return u" " * int(round(latime / spatiu))


def _rupe(rand, latime, masoara):
	"""Un rand rupt intre cuvinte in randuri de cel mult `latime` pixeli. Pe fiecare rand intra cate mai multe cuvinte
	incap (cautare prin injumatatire, putine masuri); un cuvant mai lat decat caseta ramane intreg pe randul lui."""
	if masoara(rand) <= latime:
		return [rand]
	timp, sep, text = rand.partition(SEPARATOR)
	cap = timp + sep if sep else u""
	if not sep:
		text = rand
	cuvinte = text.split(u" ")
	indent = _indent(cap, masoara)
	rez = []
	inceput = cap
	i = 0
	while i < len(cuvinte):
		jos, sus = 1, len(cuvinte) - i
		while jos < sus:
			mijloc = (jos + sus + 1) // 2
			if masoara(inceput + u" ".join(cuvinte[i:i + mijloc])) <= latime:
				jos = mijloc
			else:
				sus = mijloc - 1
		rez.append(inceput + u" ".join(cuvinte[i:i + jos]))
		i += jos
		inceput = indent
	return rez


def asezate(randuri, latime, masoara, n=RANDURI_TV, memorie=None):
	"""Randurile pasilor (Jurnal.randuri) pentru o caseta de `latime` pixeli si `n` randuri de font. masoara(text) =
	latimea in pixeli a textului pe un singur rand, cu fontul etichetei. Un rand mai lat se rupe intre cuvinte (_rupe).
	Cand randurile rupte trec de n: cererea (primul pas) si cei mai noi pasi care incap intregi. `memorie` (un dictionar
	al ferestrei) tine randurile deja rupte. Fara masura (o eroare): randurile cum sunt, cele mai noi n."""
	randuri = list(randuri or [])
	try:
		grupuri = []
		for rand in randuri:
			gata = memorie.get(rand) if memorie is not None else None
			if gata is None:
				gata = _rupe(rand, latime, masoara)
				if memorie is not None:
					if len(memorie) >= MEMORIE_MAX:
						memorie.clear()
					memorie[rand] = gata
			grupuri.append(gata)
	except Exception as e:
		print("[HdsPasiDecriptare] randurile pe televizor: %s: %s" % (type(e).__name__, e))
		return randuri[-n:] if n > 0 else []
	if sum(len(g) for g in grupuri) <= n:
		return [r for g in grupuri for r in g]
	primul = grupuri[0][:n]
	loc = n - len(primul)
	noi = []
	for g in reversed(grupuri[1:]):
		if len(g) > loc:
			break
		noi.insert(0, g)
		loc -= len(g)
	return primul + [r for g in noi for r in g]


# ---------------------------------------------------------------- jurnalul canalului de pe televizor

_STARE = {"tv": None}


def jurnal_tv():
	return _STARE["tv"]


def uita():
	"""Fara jurnal (probe; setarea oprita nu sterge nimic, doar nu mai noteaza si nu mai arata)."""
	_STARE["tv"] = None


def _modul(r, C, sloturi):
	"""Pe unde pleaca cererea: ("ci", slot, nume) prin modulul CI gata si potrivit canalului, ("soft", -1, "") cand un
	modul software asculta pe SOCKET, altfel ("", -1, "")."""
	for slot, stare, nume in sloturi:
		try:
			if stare == 2 and C.ci_slot_matches(r, slot):
				return ("ci", slot, nume)
		except Exception:
			continue
	try:
		if os.path.exists(SOCKET):
			return ("soft", -1, u"")
	except Exception:
		pass
	return ("", -1, u"")


def _sloturi(C):
	"""[(slot, stare, nume)] ale sloturilor CI: stare 0 fara modul, 1 porneste, 2 gata (eDVBCI_UI.getState)."""
	rez = []
	try:
		n = C.cam_slots()
		ui = C._ci_ui() if n > 0 else None
	except Exception:
		return rez
	if ui is None:
		return rez
	for slot in range(n):
		stare = C._ci_state(ui, slot)
		if stare in (0, 1, 2):
			rez.append((slot, stare, C.ci_module_name(slot) if stare == 2 else u""))
	return rez


def noteaza_din(r, C, d, t0, acum=None, perete=None):
	"""Chemata de Urmaritor.fotografie (numai cu setarea pornita) pentru canalul DVB redat: `r` = HdsCommon.Reader,
	`d` = fotografia ecranului negru (ref, criptat, pmt, caids, imagine), `t0` = pornirea canalului (ceasul monoton al
	urmaritorului). Intoarce randurile pentru televizor (cel mult RANDURI_TV), goale la un canal liber."""
	acum = _monoton() if acum is None else acum
	perete = time.time() if perete is None else perete
	ref = d.get("ref") or u""
	j = _STARE["tv"]
	if j is None or j.ref != ref or j.t0 != t0:
		j = Jurnal(ref, t0, perete - max(0.0, acum - t0))
		_STARE["tv"] = j
	f = {"criptat": d.get("criptat") is True, "pmt": bool(d.get("pmt")), "caids": list(d.get("caids") or []),
		"imagine": d.get("imagine")}
	if f["criptat"]:
		try:
			f["caidpids"] = list(r.caidpids())
		except Exception:
			f["caidpids"] = []
		try:
			raspuns = C.ecm_info() or {}
		except Exception:
			raspuns = {}
		# numai aceste patru campuri ies din fisierul de stare
		f["ecm"] = dict((k, raspuns[k]) for k in ("caid", "pid", "ms", "mtime") if k in raspuns)
		f["ci"] = _sloturi(C)
		if j.cerere is None:
			f["modul"] = _modul(r, C, f["ci"])
	try:
		j.noteaza(f, acum, perete)
	except Exception as e:
		print("[HdsPasiDecriptare] %s: %s" % (type(e).__name__, e))
	return j.randuri(RANDURI_TV, C)


def mesaj_ci(slot, ecran, acum=None):
	"""Un ecran MMI al unui modul CI (lista din getMMIScreen: ("TITLE", text), ("TEXT", text, ...), ...), dat de
	Screens/Ci.py cand il arata. Cu setarea pornita, titlul si textele lui intra in jurnalul canalului de pe televizor."""
	if not pornit():
		return
	j = _STARE["tv"]
	if j is None or not ecran:
		return
	parti = []
	try:
		for intrare in ecran:
			if len(intrare) > 1 and intrare[0] in ("TITLE", "SUBTITLE", "TEXT", "BOTTOM"):
				t = _curat(intrare[1], MESAJ_CI_MAX)
				if t and t not in parti:
					parti.append(t)
	except Exception:
		return
	if parti:
		j.mesaj_ci(u" · ".join(parti), _monoton() if acum is None else acum)


def date_web(C=None):
	"""Pentru GET /api/pasi-decriptare: {result, pornit, ref, criptat, decriptat, pasi: [{t, text, fel}]}. Setarea
	oprita: lista goala, fara nicio citire."""
	corp = {"result": True, "pornit": False, "ref": u"", "criptat": False, "decriptat": False, "pasi": []}
	if not pornit():
		return corp
	corp["pornit"] = True
	j = _STARE["tv"]
	if j is None:
		return corp
	corp.update({"ref": j.ref, "criptat": j.criptat is True, "decriptat": j.img is True, "pasi": j.web(RANDURI_WEB, C)})
	return corp
