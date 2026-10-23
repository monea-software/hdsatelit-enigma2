# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Culegerea unita a valorilor vii ale canalului care ruleaza, in baza unica (Components/HdsBazaCanale.py), si ceasurile
bazei (incarcarea, scrierea, migrarea, standby, oprirea).

CE SE CULEGE (un singur ascultator pe session.nav.event; valorile intra in baza prin actualizeaza, sursa "v"):
  evStart        nimic citit: citirile in curs se opresc, canalul se noteaza "vazut" (numai in memorie), iar imaginea se
                 citeste dupa VIDEO_PORNIRE_MS (pentru driverele care nu anunta nimic);
  evUpdatedInfo  dupa LINISTE_MS fara alt evUpdatedInfo: accesul (sIsCrypted, CAID-urile, PID-urile ECM) si PID-urile
                 (PMT, PCR, video, teletext, AIT din sAITPID), numai cand PMT-ul s-a citit (sPMTPID > 0; inainte sunt
                 date din cache); HbbTV din nucleu (grupele hb si ap, Components/HdsHbbtv.grupe_baza);
  evHBBTVInfo    dupa HBBTV_MS: numai grupele hb si ap, din AIT-ul citit de nucleu (hb = 1 numai cu o aplicatie de
                 pornit in AIT, hb = 0 numai cand PMT-ul nu are AIT HbbTV), pe un canal DVB cu PMT-ul citit;
                 pistele (limbile sunetului, subtitrarile, teletextul) dupa setarea „Citirea pistelor la vizionare”:
                 oprita = fara piste, canal = prin nucleu, transponder = si PMT-ul brut al transponderului (sursa "p",
                 cu HbbTV), ca inainte (HdsPisteCanale.Culegator);
  imaginea       la VIDEO_MS dupa evVideoSizeChanged / ProgressiveChanged / FramerateChanged / GammaChanged: latimea,
                 inaltimea, progresiv, cadrele pe secunda, gama, aspectul, codecul, numai cu inaltimea > 0 (decodorul a
                 dat un cadru); cu inaltimea 0 (canal criptat nedecodat) numai codecul, cum se nota si inainte, si numai
                 cand baza nu stie inaltimea canalului (altfel imaginea nevazuta ar lua data de azi).
  O valoare stiuta nu se inlocuieste cu "nu se stie", iar o valoare egala cu cea din baza e numai o confirmare in
  memorie (HdsBazaCanale): o zi de zapuri pe canale stiute nu scrie nimic pe disc. La prima nota pe o cheie fara rand
  in baza, randul ramas sub cheia veche dupa o rescanare pe alta frecventa se uneste sub cheia noua (cauta cu
  rezerva=True), numai cand baza are un singur alt rand pe cheia de rezerva, iar lamedb un singur serviciu pe ea si
  acela e chiar canalul redat.
  Cat culegerea merge, accesul nu se mai noteaza din afisaj (HdsAccesCanale.lasa_notarea_culegerii).
  Dupa fiecare nota se cheama ascultatorii (asculta / nu_mai_asculta) cu cheia si grupele: asa afla culegerea canal cu
  canal (Components/HdsCulegereTotala.py) ca un canal pornit de ea e gata.

CEASURILE BAZEI (Pornire):
  INCARCARE_MS dupa pornirea culegerii (din lista de canale, dupa primul ecran): baza().incarca(), cu versiunea
    imaginii pentru antet;
  la fiecare TIC_MS: reincearca() (numai din numai-citire; baza asteapta singura intre incercari) si salveaza(PRAG)
    (scrie numai o baza murdara, dupa prag si sub bugetul zilei);
  MIGRARE_MS: migrarea din fisierele de dinainte (HdsBazaCanale.Migrare), numai dupa o pornire curata (nicio oprire
    neasteptata a interfetei in ultimele FEREASTRA_CADERI_S secunde, dupa /tmp/hds-enigma2.caderi scris de
    enigma2.sh) si in afara unei inregistrari; altfel, sau cu ceasul receptorului nepotrivit, se incearca din nou la
    fiecare tic. Migrarea merge pe bucati: cel mult FELIE_MIGRARE_S de lucru pe o chemare a ceasului, apoi
    PAUZA_MIGRARE_MS pentru interfata;
  dupa migrare: unirea bazei de pornire (Components/HdsBazaPornire.Unire), tot pe felii, cu aceleasi conditii (pornire
    curata, nicio inregistrare); se reia la tic dupa o descarcare noua de pe stb.hdsatelit.com, cand lamedb-ul s-a
    schimbat (o scanare) sau cand a asteptat ceasul ori o baza care se poate scrie;
  la fiecare tic, descarcarea zilnica a bazei de pe stb (HdsBazaPornire.Zilnic), numai cu setarea "Ia baza de canale de
    pe stb.hdsatelit.com" pornita (oprita din fabrica);
  standby: salveaza(STANDBY, sincron=True), prin config.misc.standbyCounter, cu initial_call=False (altfel s-ar scrie
    la fiecare pornire a interfetei).
  Oprirea interfetei: la_oprire() din mytest.py. Resetarea din fabrica si flash-ul: opreste_scrierile(); inaintea
  copiei de dinaintea flash-ului: inainte_de_copie().

Partea de sus e curata: enigma (eTimer, iPlayableService, iServiceInformation, config) se importa tarziu, deci
modulul se probeaza pe PC (test_culegere_canale.py).
"""

from __future__ import absolute_import

import errno
import os
import time

try:
	from Components import HdsBazaCanale as B
	from Components import HdsIndexCanale as X
	from Components import HdsPisteCanale as P
	from Components import HdsAccesCanale as A
	from Components import HdsBazaPornire as BP
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsBazaCanale as B
	import HdsIndexCanale as X
	import HdsPisteCanale as P
	import HdsAccesCanale as A
	import HdsBazaPornire as BP

LINISTE_MS = 2500
VIDEO_MS = 1500
HBBTV_MS = 500
VIDEO_PORNIRE_MS = 6000
INCARCARE_MS = 2000
TIC_MS = 60000
MIGRARE_MS = 90000
FELIE_MIGRARE_S = 0.05
PAUZA_MIGRARE_MS = 20

CALE_CADERI = "/tmp/hds-enigma2.caderi"
CALE_UPTIME = "/proc/uptime"
FEREASTRA_CADERI_S = 600
MAX_LAMEDB = 32 * 1024 * 1024

# sAspect (codurile decodorului, ca in Converter/HdsCommon.py)
ASPECT_LAT = (3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10)
ASPECT_43 = (1, 2, 5, 6, 9, 0xA, 0xD, 0xE)

# starea migrarii in aceasta pornire
ASTEAPTA, AMANATA, IN_CURS, GATA = "asteapta", "amanata", "in-curs", "gata"


def _jurnal(text):
	print("[HdsCulegereCanale] %s" % text)


# ---------------------------------------------------------------- valorile din nucleu (curat)

def _info_int(info, c, nume):
	w = getattr(c, nume, None)
	if w is None or info is None:
		return -1
	try:
		v = info.getInfo(w)
	except Exception:
		return -1
	return v if isinstance(v, int) and not isinstance(v, bool) else -1


def _info_obiect(info, c, nume):
	w = getattr(c, nume, None)
	if w is None or info is None:
		return None
	try:
		return info.getInfoObject(w)
	except Exception:
		return None


def valori_video(info, c):
	"""Grupa vd din decodor: [latime, inaltime, progresiv, cadre, gama, aspect, codec]; cu inaltimea 0 numai codecul;
	None daca nu se stie nimic (fara imagine, radio)."""
	inaltime = _info_int(info, c, "sVideoHeight")
	tip = _info_int(info, c, "sVideoType")
	cod = X.COD_DIN_SVIDEOTYPE.get(tip, "alt" if tip >= 0 else "")
	if inaltime <= 0:
		return [-1, -1, -1, -1, -1, "", cod] if cod else None
	latime = _info_int(info, c, "sVideoWidth")
	progresiv = _info_int(info, c, "sProgressive")
	cadre = _info_int(info, c, "sFrameRate")
	gama = _info_int(info, c, "sGamma")
	a = _info_int(info, c, "sAspect")
	aspect = "16:9" if a in ASPECT_LAT else ("4:3" if a in ASPECT_43 else "")
	return [latime if latime > 0 else -1, inaltime, progresiv if progresiv in (0, 1) else -1, cadre if cadre > 0 else -1,
		gama if 0 <= gama <= 3 else -1, aspect, cod]


def _caid(v):
	try:
		c = int(v) & 0xFFFF
	except Exception:
		return 0
	return c


def valori_acces(info, c):
	"""Grupa ca: [0 FTA / 1 criptat, [[CAID, PID ECM], ...]] (PID -1 cand nu se stie), sau None cat nu se stie."""
	perechi, vazute = [], set()
	obiect = _info_obiect(info, c, "sCAIDPIDs")
	for e in obiect if isinstance(obiect, (list, tuple)) else ():
		try:
			caid = _caid(e[0])
		except Exception:
			continue
		try:
			pid = int(e[1])
		except Exception:
			pid = -1
		if not 0 < pid < 0x1FFF:
			pid = -1
		if caid and (caid, pid) not in vazute:
			vazute.add((caid, pid))
			perechi.append([caid, pid])
	obiect = _info_obiect(info, c, "sCAIDs")
	caids = sorted(set(x for x in (_caid(v) for v in (obiect if isinstance(obiect, (list, tuple)) else ())) if x))
	cu_pid = set(p[0] for p in perechi)
	perechi.extend([x, -1] for x in caids if x not in cu_pid)
	criptat = _info_int(info, c, "sIsCrypted")
	if perechi or criptat == 1:
		return [1, sorted(perechi)]
	if criptat == 0:
		return [0, []]
	return None


def valori_pmt(info, c):
	"""Grupa pmt: [PID PMT, PCR, video, stream_type video, teletext, AIT] (-1 = nu se stie; AIT 0 = fara AIT HbbTV,
	din sAITPID), sau None fara PMT."""
	pmt = _info_int(info, c, "sPMTPID")
	if not 0 < pmt < 0x1FFF:
		return None

	def pid(nume):
		v = _info_int(info, c, nume)
		return v if 0 < v < 0x1FFF else -1
	ait = _info_int(info, c, "sAITPID")
	return [pmt, pid("sPCRPID"), pid("sVideoPID"), -1, pid("sTXTPID"), ait if 0 <= ait < 0x1FFF else -1]


_HBBTV = []


def _hbbtv():
	"""Components/HdsHbbtv (cautat o singura data), sau None: fara el culegerea merge mai departe, numai fara grupele
	hb si ap din nucleu."""
	if not _HBBTV:
		try:
			try:
				from Components import HdsHbbtv as H
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				import HdsHbbtv as H
		except Exception as e:
			_jurnal("HdsHbbtv: %s" % e)
			H = None
		_HBBTV.append(H)
	return _HBBTV[0]


def valori_hbbtv(info, c):
	"""Grupele hb si ap din AIT-ul citit de nucleu (Components/HdsHbbtv.grupe_baza), numai ce se stie; {} pe un nucleu
	fara sAITPID, cat AIT-ul nu s-a citit sau fara modulul HdsHbbtv."""
	H = _hbbtv()
	if H is None:
		return {}
	try:
		return H.grupe_baza(H.din_info(info, c))
	except Exception as e:
		_jurnal("HbbTV: %s" % e)
		return {}


def pistele(rec):
	"""Inregistrarea pistelor (HdsPisteCanale.din_serviciu) -> grupele pi si hb ale bazei."""
	grupe = {}
	pi = dict((k, rec[k]) for k in ("a", "d", "x", "tt") if k in rec)
	if pi:
		grupe["pi"] = pi
	if "hb" in rec:
		grupe["hb"] = rec["hb"]
	return grupe


def pornire_curata(cale_caderi=CALE_CADERI, cale_uptime=CALE_UPTIME):
	"""True daca interfata nu s-a oprit neasteptat in ultimele FEREASTRA_CADERI_S secunde: fisierul caderilor are
	randuri "<secunde de la pornirea receptorului> <cod>". Fara fisier: curata. Cu fisier, dar fara ceasul de pornire
	(/proc/uptime), sau fisierul necitit: nu se poate sti, deci nu. Secundele se iau intregi, ca in enigma2.sh
	(cut -d. -f1 /proc/uptime), deci fereastra e aceeasi cu a garzii de acolo."""
	try:
		with open(cale_caderi, "r") as f:
			text = f.read(16384)
	except (IOError, OSError) as e:
		return getattr(e, "errno", None) in (errno.ENOENT, errno.ENOTDIR)
	except ValueError:
		# octeti care nu sunt text (UnicodeDecodeError): fisierul nu se poate citi, deci nu se stie
		return False
	try:
		with open(cale_uptime, "r") as f:
			acum = int(float(f.read(64).split()[0]))
	except (IOError, OSError, ValueError, IndexError):
		return False
	for linie in text.splitlines():
		parti = linie.split()
		try:
			t = float(parti[0])
		except (ValueError, IndexError):
			continue
		if t + FEREASTRA_CADERI_S >= acum:
			return False
	return True


def _servicii_lamedb(text):
	"""Cheile serviciilor din lamedb, in forma cheii bazei (sectiunea services, primul rand al fiecarui serviciu:
	"sid:ns:tsid:onid:tip:numar")."""
	randuri = text.split("\n")
	n = len(randuri)
	i = 0
	while i < n and randuri[i].strip() != "services":
		i += 1
	i += 1
	while i < n and randuri[i].strip() != "end":
		parti = randuri[i].strip().split(":")
		i += 3
		if len(parti) < 4:
			continue
		try:
			sid, ns, tsid, onid = [int(x, 16) for x in parti[:4]]
		except ValueError:
			continue
		yield "%x:%x:%x:%x" % (sid, ns, tsid, onid)


def numara_rezerve_lamedb(text):
	"""{cheie de rezerva: numarul serviciilor din lamedb cu ea}."""
	rez = {}
	for k in _servicii_lamedb(text):
		r = B.cheie_rezerva(k)
		if r:
			rez[r] = rez.get(r, 0) + 1
	return rez


def harta_rezerve_lamedb(text):
	"""{cheie de rezerva: namespace-ul singurului serviciu cu ea (>= 0), sau minus numarul serviciilor cand sunt mai
	multe}: un intreg pe cheie, nu cheia intreaga, ca harta sa ramana mica."""
	rez = {}
	for k in _servicii_lamedb(text):
		r = B.cheie_rezerva(k)
		if not r:
			continue
		e = rez.get(r)
		rez[r] = int(k.split(":")[1], 16) if e is None else (-2 if e >= 0 else e - 1)
	return rez


class RezerveLamedb(object):
	"""Serviciile din lamedb pe o cheie de rezerva: cate sunt si, cand e unul singur, care e. lamedb se citeste numai la
	cerere (dupa o rescanare, cand baza are un rand sub alta cheie) si din nou numai cand s-a schimbat."""

	def __init__(self, cale=os.path.join(B.DOSAR_VECHI, "lamedb")):
		self.cale = cale
		self._semn = None
		self._harta = {}
		self.citiri = 0

	def _la_zi(self):
		try:
			st = os.stat(self.cale)
		except (IOError, OSError):
			return False
		semn = (st.st_mtime, st.st_size)
		if semn != self._semn:
			try:
				with open(self.cale, "rb") as f:
					text = f.read(MAX_LAMEDB).decode("utf-8", "replace")
			except (IOError, OSError):
				return False
			self.citiri += 1
			self._harta = harta_rezerve_lamedb(text)
			self._semn = semn
		return True

	def numar(self, rezerva):
		e = self._harta.get(rezerva) if self._la_zi() else None
		if e is None:
			return 0
		return 1 if e >= 0 else -e

	def singurul(self, rezerva):
		"""Cheia singurului serviciu din lamedb pe cheia de rezerva, sau None (niciunul sau mai multe)."""
		e = self._harta.get(rezerva) if self._la_zi() else None
		if e is None or e < 0:
			return None
		try:
			parti, _poz = rezerva.split("@", 1)
			onid, tsid, sid = [int(x, 16) for x in parti.split(":")]
		except ValueError:
			return None
		return "%x:%x:%x:%x" % (sid, e, tsid, onid)


def versiune_imagine():
	"""Versiunea care ruleaza („0.1.5”) din jurnalul versiunilor, sau "" daca nu se stie."""
	try:
		try:
			from Components import HdsJurnalVersiuni as J
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			import HdsJurnalVersiuni as J
		v = J.versiunea_care_ruleaza()
	except Exception:
		return ""
	return v.get("versiune", "") if isinstance(v, dict) else ""


# ---------------------------------------------------------------- culegerea

class Culegere(P.Culegator):
	"""Culegatorul unit. Citirea bruta a transponderului si oprirea pe timpul lui „Actualizeaza” (opreste_pentru) sunt
	ale lui HdsPisteCanale.Culegator; aici se culeg si accesul, PID-urile si imaginea, iar pistele numai dupa PMT pe un
	canal DVB. Pe timpul lui „Actualizeaza” (pauza) nu se citesc pistele (le citeste ea), dar accesul, PID-urile si
	imaginea da. Scrierea pe disc e a bazei (Pornire), nu a culegatorului."""

	def __init__(self, nav, b=None, fabrica_ceas=None, cititor=None, evenimente=None, info_const=None, ceasornic=None,
			mod=None, rezerve=None):
		if info_const is None:
			from enigma import iServiceInformation as info_const
		self.b = b if b is not None else B.baza()
		P.Culegator.__init__(self, nav, P.BazaUnica(B, self.b), fabrica_ceas, cititor, evenimente, info_const,
			ceasornic, mod)
		try:
			fabrica = fabrica_ceas or P._ceasEnigma
			self.ceasVideo = fabrica()
			self.ceasVideo.callback.append(self._citesteVideo)
			self.ceasHbbtv = fabrica()
			self.ceasHbbtv.callback.append(self._citesteHbbtv)
			self._ev_hbbtv = getattr(self.ev, "evHBBTVInfo", None)
			# urmaritorul HbbTV (Components/HdsHbbtv.Urmaritor) primeste evenimentele de aici: un singur ascultator
			self.urmaritor_hbbtv = None
			# la fel istoricul semnalului (Components/HdsIstoricSemnal.Urmaritor)
			self.urmaritor_semnal = None
			self._ev_video = tuple(x for x in (getattr(self.ev, n, None) for n in ("evVideoSizeChanged",
				"evVideoProgressiveChanged", "evVideoFramerateChanged", "evVideoGammaChanged")) if x is not None)
			self.rezerve = rezerve if rezerve is not None else RezerveLamedb()
			self._chei = set()
			self.note = 0
		except Exception:
			# P.Culegator a pus deja _eveniment in nav.event: un ascultator pe jumatate facut ar arunca la fiecare zap
			# (dispatchEvent e chemat din C++), deci se retrage, iar apelantul trece pe culegerea de dinainte
			self._retrage(mod is None)
			raise

	def _retrage(self, cu_setarea):
		try:
			self.nav.event.remove(self._eveniment)
		except ValueError:
			pass
		if cu_setarea:
			try:
				lista = P.initConfig().notifiers
				while self.laSchimbareSetare in lista:
					lista.remove(self.laSchimbareSetare)
			except Exception as e:
				_jurnal("setarea culegerii: %s" % e)

	def laSchimbareSetare(self, *argumente):
		"""Setarea pistelor schimbata: numai citirea bruta se opreste (accesul si imaginea nu depind de setare)."""
		if self.mod() != P.CULEGERE_TRANSPONDER:
			self.cititor.opreste()

	def _eveniment(self, ev):
		# chemat din C++ (Navigation.dispatchEvent, fara try): o exceptie scapata de aici opreste interfata
		try:
			e = self.ev
			if ev == e.evStart:
				self.ceas.stop()
				self.cititor.opreste()
				self.ceasHbbtv.stop()
				self.ceasVideo.start(VIDEO_PORNIRE_MS, True)
				self._vazut()
			elif ev == getattr(e, "evEnd", None):
				self.ceas.stop()
				self.cititor.opreste()
				self.ceasVideo.stop()
				self.ceasHbbtv.stop()
			elif ev == e.evUpdatedInfo:
				self.ceas.start(self.LINISTE_MS, True)
			elif ev in self._ev_video:
				self.ceasVideo.start(VIDEO_MS, True)
			elif self._ev_hbbtv is not None and ev == self._ev_hbbtv:
				self.ceasHbbtv.start(HBBTV_MS, True)
			if self.urmaritor_hbbtv is not None:
				self.urmaritor_hbbtv.eveniment(ev)
			if self.urmaritor_semnal is not None:
				self.urmaritor_semnal.eveniment(ev)
		except Exception as ex:
			_jurnal("eveniment %s: %s" % (ev, ex))

	def _vazut(self):
		try:
			ref = self.nav.getCurrentlyPlayingServiceReference()
			if ref is not None:
				self.b.vazut(ref.toString(), self.ceasornic())
		except Exception as e:
			_jurnal("vazut: %s" % e)

	def _curent(self):
		"""(referinta text, cheia, serviciul) canalului care ruleaza, sau None."""
		ref = self.nav.getCurrentlyPlayingServiceReference()
		service = self.nav.getCurrentService()
		text = ref.toString() if ref is not None else ""
		k = X.cheie_din_ref(text) if text else None
		if not k or service is None:
			return None
		return text, k, service

	def _cheia(self, k):
		"""Prima nota pe o cheie in aceasta pornire, numai cand baza nu are rand pentru ea (o ratare: harta cheilor de
		rezerva a bazei se face abia atunci): randul ramas sub cheia de dinaintea unei rescanari se uneste sub k, numai
		cu un singur alt rand in baza pe cheia de rezerva si cu un singur serviciu in lamedb pe ea, care e chiar k (cand
		e cel vechi, lamedb nu s-a scris inca dupa rescanare sau canalul vechi exista: nu se ghiceste)."""
		if k in self._chei:
			return
		self._chei.add(k)
		try:
			if self.b.contine(k) or self.b.candidat_rezerva(k) is None:
				return
			r = B.cheie_rezerva(k)
			if r and self.rezerve.singurul(r) == k:
				self.b.cauta(k, rezerva=True)
		except Exception as e:
			_jurnal("cheia de rezerva: %s" % e)

	def _noteaza(self, k, grupe):
		self._cheia(k)
		self.note += 1
		rez = self.b.actualizeaza(k, grupe, "v", self.ceasornic())
		_anunta(k, grupe)
		return rez

	def _citeste(self):
		try:
			curent = self._curent()
			if curent is None:
				return
			text, k, service = curent
			info = service.info()
			c = self.info_const
			dvb = P.transponder_din_ref(text) is not None
			pmt = valori_pmt(info, c)
			grupe = {}
			if dvb and pmt is not None:
				grupe["pmt"] = pmt
				ca = valori_acces(info, c)
				if ca is not None:
					grupe["ca"] = ca
			mod = self.mod()
			piste = mod != P.CULEGERE_OPRITA and not self.pauza
			if piste and (pmt is not None or not dvb):
				self.citiri += 1
				rec = P.din_serviciu(service, c)
				if rec is not None:
					grupe.update(pistele(rec))
			if dvb and pmt is not None:
				grupe.update(valori_hbbtv(info, c))
			if grupe:
				self._noteaza(k, grupe)
			if piste and dvb and mod == P.CULEGERE_TRANSPONDER:
				self._citesteTransponder(text, service)
		except Exception as e:
			_jurnal("culegere: %s" % e)

	def _citesteHbbtv(self):
		"""AIT-ul citit de nucleu (evHBBTVInfo): numai grupele hb si ap, pe un canal DVB cu PMT-ul citit."""
		try:
			curent = self._curent()
			if curent is None:
				return
			text, k, service = curent
			info = service.info()
			if P.transponder_din_ref(text) is None or valori_pmt(info, self.info_const) is None:
				return
			grupe = valori_hbbtv(info, self.info_const)
			if grupe:
				self._noteaza(k, grupe)
		except Exception as e:
			_jurnal("HbbTV: %s" % e)

	def _citesteVideo(self):
		try:
			curent = self._curent()
			if curent is None:
				return
			_text, k, service = curent
			vd = valori_video(service.info(), self.info_const)
			if vd is None:
				return
			if vd[1] <= 0:
				# numai codecul: nimic de spus despre o imagine stiuta (nici confirmare, nici data noua)
				self._cheia(k)
				if self._inaltime_stiuta(k):
					return
			self._noteaza(k, {"vd": vd})
		except Exception as e:
			_jurnal("imaginea: %s" % e)

	def _inaltime_stiuta(self, k):
		rec = self.b.cauta(k)
		vd = B.valoare_grupa(rec, "vd") if rec else None
		return isinstance(vd, list) and len(vd) > 1 and isinstance(vd[1], int) and vd[1] > 0

	def _programeazaScrierea(self):
		"""Scrierea pe disc e a bazei (ticul din Pornire), nu la 30 s dupa fiecare culegere."""


# ---------------------------------------------------------------- ceasurile bazei

class Pornire(object):
	"""Incarcarea, scrierea la prag, reincercarea, migrarea si standby-ul bazei (vezi antetul modulului)."""

	def __init__(self, b, nav=None, fabrica_ceas=None, config_=None, curata=None, versiune=None, dosar=B.DOSAR_VECHI,
			migreaza=None, cronometru=None, unire=None, zilnic=None, stb_activ=None):
		"""migreaza: o functie dintr-o bucata (b, dosar) -> {fisier: stare}, in locul migrarii pe bucati (probe);
		cronometru: ceasul felilor de migrare si de unire (secunde, numai diferente); unire: b -> un obiect cu pas() si
		rez (implicit HdsBazaPornire.Unire pe fisierele din `dosar`); zilnic, stb_activ: descarcarea de pe stb si setarea
		ei (probe)."""
		self.b = b
		self.nav = nav
		self.curata = curata or pornire_curata
		self.versiune = versiune or versiune_imagine
		self.dosar = dosar
		self._migreaza = migreaza
		self._cronometru = cronometru or getattr(time, "monotonic", time.time)
		self._pasi = None
		self.migrare = ASTEAPTA
		self.unire = ASTEAPTA
		self._unire = unire or self._unire_implicita
		self._unirePasi = None
		self._reiaUnirea = False
		self.cale_lamedb = os.path.join(dosar, "lamedb")
		self._amprentaLamedb = None
		self.zilnic = zilnic or BP.Zilnic()
		self._stb_activ = stb_activ or BP.stb_activ
		fabrica = fabrica_ceas or P._ceasEnigma
		self.ceasIncarcare = fabrica()
		self.ceasIncarcare.callback.append(self._incarca)
		self.ceasMigrare = fabrica()
		self.ceasMigrare.callback.append(self._laMigrare)
		self.ceasTic = fabrica()
		self.ceasTic.callback.append(self._tic)
		self.ceasUnire = fabrica()
		self.ceasUnire.callback.append(self._laUnire)
		self.ceasIncarcare.start(INCARCARE_MS, True)
		self.ceasMigrare.start(MIGRARE_MS, True)
		self.ceasTic.start(TIC_MS, False)
		try:
			if config_ is None:
				from Components.config import config as config_
			config_.misc.standbyCounter.addNotifier(self._laStandby, initial_call=False)
		except Exception as e:
			_jurnal("standby: %s" % e)

	def _incarca(self):
		try:
			self.b.seteaza_imagine(self.versiune())
			self.b.incarca()
		except Exception as e:
			_jurnal("incarcarea: %s" % e)

	def _laStandby(self, *argumente):
		try:
			self.b.salveaza(B.STANDBY, sincron=True)
		except Exception as e:
			_jurnal("scrierea la standby: %s" % e)

	def _permisa(self):
		if not self.curata():
			return False
		try:
			if self.nav is not None and self.nav.getRecordings():
				return False
		except Exception:
			pass
		return True

	def _incearcaMigrarea(self):
		if not self._permisa():
			if self.migrare == ASTEAPTA:
				_jurnal("migrarea amanata: oprire neasteptata recenta sau inregistrare in curs")
			self.migrare = AMANATA
			return
		self.migrare = IN_CURS
		if self._migreaza is not None:
			try:
				rez = self._migreaza(self.b, self.dosar)
			except Exception as e:
				_jurnal("migrarea: %s" % e)
				rez = None
			self._dupaMigrare(rez)
			return
		try:
			self._pasi = B.Migrare(self.b, self.dosar)
		except Exception as e:
			_jurnal("migrarea: %s" % e)
			self._dupaMigrare(None)
			return
		self._pasMigrare()

	def _pasMigrare(self):
		"""Bucati de migrare cat tine o felie (FELIE_MIGRARE_S); daca mai e de lucru, ceasul migrarii o reia dupa
		PAUZA_MIGRARE_MS, ca interfata sa nu stea (paznicul o reporneste dupa 60 s fara bataie)."""
		inceput = self._cronometru()
		try:
			while self._pasi.pas():
				if self._cronometru() - inceput >= FELIE_MIGRARE_S:
					self.ceasMigrare.start(PAUZA_MIGRARE_MS, True)
					return
		except Exception as e:
			_jurnal("migrarea: %s" % e)
		rez, self._pasi = self._pasi.rez, None
		self._dupaMigrare(rez)

	def _dupaMigrare(self, rez):
		# un fisier lasat pentru ceasul nepotrivit se reia la tic, in aceeasi pornire; restul, la pornirea urmatoare
		if isinstance(rez, dict) and B.CEAS_NEPOTRIVIT in rez.values():
			self.migrare = AMANATA
		else:
			self.migrare = GATA
			if self.unire == ASTEAPTA:
				self.ceasUnire.start(PAUZA_MIGRARE_MS, True)

	def _laMigrare(self):
		try:
			if self.migrare == IN_CURS and self._pasi is not None:
				self._pasMigrare()
			elif self.migrare == ASTEAPTA:
				self._incearcaMigrarea()
		except Exception as e:
			_jurnal("migrarea: %s" % e)

	# ------------------------------------------------ baza de pornire (Components/HdsBazaPornire.py)

	def _unire_implicita(self, b):
		return BP.Unire(b, cale_stb=os.path.join(self.dosar, os.path.basename(BP.CALE_STB)), cale_lamedb=self.cale_lamedb)

	def _incearcaUnirea(self):
		if not self._permisa():
			if self.unire == ASTEAPTA:
				_jurnal("unirea bazei de pornire amanata: oprire neasteptata recenta sau inregistrare in curs")
			self.unire = AMANATA
			return
		self.unire = IN_CURS
		self._reiaUnirea = False
		self._amprentaLamedb = BP.amprenta(self.cale_lamedb)
		try:
			self._unirePasi = self._unire(self.b)
		except Exception as e:
			_jurnal("unirea bazei de pornire: %s" % e)
			self._dupaUnire(None)
			return
		self._pasUnire()

	def _pasUnire(self):
		"""Ca migrarea: cat tine o felie (FELIE_MIGRARE_S), apoi ceasul unirii o reia dupa PAUZA_MIGRARE_MS."""
		inceput = self._cronometru()
		try:
			while self._unirePasi.pas():
				if self._cronometru() - inceput >= FELIE_MIGRARE_S:
					self.ceasUnire.start(PAUZA_MIGRARE_MS, True)
					return
		except Exception as e:
			_jurnal("unirea bazei de pornire: %s" % e)
		rez, self._unirePasi = getattr(self._unirePasi, "rez", None), None
		self._dupaUnire(rez)

	def _dupaUnire(self, rez):
		# un fisier care a asteptat ceasul sau o baza care se poate scrie se reia la tic, in aceeasi pornire
		if isinstance(rez, dict) and (BP.CEAS in rez.values() or BP.NESCRIS in rez.values()):
			self.unire = AMANATA
		else:
			self.unire = GATA

	def _laUnire(self):
		try:
			if self.unire == IN_CURS and self._unirePasi is not None:
				self._pasUnire()
			elif self.unire in (ASTEAPTA, AMANATA) and self.migrare == GATA:
				self._incearcaUnirea()
		except Exception as e:
			_jurnal("unirea bazei de pornire: %s" % e)

	def _ticUnire(self):
		"""Descarcarea zilnica (cu setarea pornita) si reluarea unirii dupa o baza noua sau un lamedb schimbat."""
		if self.zilnic.pas(bool(self._stb_activ())) == BP.NOU:
			self._reiaUnirea = True
		if self.migrare != GATA or self.unire in (ASTEAPTA, IN_CURS):
			return
		if self.unire == GATA and (self._reiaUnirea or BP.amprenta(self.cale_lamedb) != self._amprentaLamedb):
			self.unire = AMANATA
		if self.unire == AMANATA:
			self._incearcaUnirea()

	def _tic(self):
		try:
			self.b.reincearca()
			if self.migrare == AMANATA:
				self._incearcaMigrarea()
		except Exception as e:
			_jurnal("tic: %s" % e)
		try:
			self._ticUnire()
		except Exception as e:
			_jurnal("tic, baza de pornire: %s" % e)
		try:
			self.b.salveaza(B.PRAG)
		except Exception as e:
			_jurnal("tic: %s" % e)


# ---------------------------------------------------------------- ascultatorii notelor

_ASCULTATORI = []


def asculta(functie):
	"""functie(cheie, grupe) dupa fiecare nota a culegerii (si cand valoarea e egala cu cea din baza, si cand o valoare
	volatila asteapta a doua vizionare): culegerea canal cu canal (Components/HdsCulegereTotala.py) afla asa ca un canal
	e gata. Chemata pe firul enigma2; o exceptie a ei ramane aici."""
	if functie not in _ASCULTATORI:
		_ASCULTATORI.append(functie)


def nu_mai_asculta(functie):
	while functie in _ASCULTATORI:
		_ASCULTATORI.remove(functie)


def _anunta(k, grupe):
	for functie in list(_ASCULTATORI):
		try:
			functie(k, grupe)
		except Exception as e:
			_jurnal("ascultatorul notelor: %s" % e)


# ---------------------------------------------------------------- legaturile cu restul imaginii

_STARE = {"culegere": None, "pornire": None}


def porneste(session):
	"""O singura data (din lista de canale, Screens/HdsCautareCanale.porneste_culegator): culegerea unita si ceasurile
	bazei. -> culegerea (are opreste_pentru, pentru „Actualizeaza”)."""
	if _STARE["culegere"] is None:
		b = B.baza()
		# intai ceasurile bazei: daca culegatorul nu porneste, baza tot se incarca, se scrie si se migreaza, iar
		# culegerea de dinainte (aleasa de apelant) noteaza prin adaptoare, cu accesul notat din afisaj ca inainte
		if _STARE["pornire"] is None:
			_STARE["pornire"] = Pornire(b, session.nav)
		_STARE["culegere"] = Culegere(session.nav, b)
		A.lasa_notarea_culegerii()
		H = _hbbtv()
		if H is not None:
			try:
				_STARE["culegere"].urmaritor_hbbtv = H.porneste(session, pe_nav=False)
			except Exception as e:
				_jurnal("urmaritorul HbbTV: %s" % e)
		# istoricul semnalului pe pozitii si transpondere: evenimentele de la culegere (tot un singur ascultator pe
		# navigatie), o citire a tunerului pe zap
		try:
			from Components import HdsIstoricSemnal
			_STARE["culegere"].urmaritor_semnal = HdsIstoricSemnal.porneste(session.nav, pe_nav=False)
		except Exception as e:
			_jurnal("istoricul semnalului: %s" % e)
	return _STARE["culegere"]


def activ():
	return _STARE["culegere"] is not None


def la_oprire():
	"""Oprirea sau repornirea interfetei (mytest.py, dupa runReactor): scrierea sincrona numai daca baza e murdara."""
	_istoric("la_oprire")
	b = B.baza_existenta()
	return b.la_oprire() if b is not None else False


def _istoric(nume):
	"""Istoricul semnalului (Components/HdsIstoricSemnal.py) la oprire, copie si resetare; nu arunca."""
	try:
		from Components import HdsIstoricSemnal
		getattr(HdsIstoricSemnal, nume)()
	except Exception as e:
		_jurnal("istoricul semnalului, %s: %s" % (nume, e))


def opreste_scrierile():
	"""Inaintea resetarii din fabrica si a flash-ului: nicio scriere a bazei pana la repornirea interfetei."""
	_istoric("opreste_scrierile")
	B.baza().opreste_scrierile()


class Scrieri(object):
	"""Pentru codul din data/menu.xml (resetarea din fabrica): Scrieri.opreste() = opreste_scrierile()."""

	@staticmethod
	def opreste():
		opreste_scrierile()


def inainte_de_copie():
	"""Inaintea copiei de siguranta: baza murdara se scrie acum, ca sa intre in copie."""
	_istoric("inainte_de_copie")
	b = B.baza_existenta()
	return b.salveaza(B.COPIE, sincron=True) if b is not None else False
