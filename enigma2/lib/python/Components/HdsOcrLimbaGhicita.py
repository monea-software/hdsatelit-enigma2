# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsOcrLimbaGhicita.py: limba unei subtitrari DVB fara limba declarata, ghicita dupa canal, ca recunoasterea textului
# (Components/HdsOcrSubtitrari.py) sa citeasca pozele cu modelul acelei limbi.
#
# DE CE: o pista DVB fara limba (und, qaa, gol) se citea cu modelul romanesc. Pe paginile in alte limbi latine modelul
# romanesc greseste 5,6 % din litere si scrie diacriticele gresit, iar modelul limbii adevarate 0,16 % (masurat pe
# pagini reale). Modelul general al alfabetului latin ar fi ajutat, dar ia ~270 MB de memorie; de aceea: fara el,
# limba ghicita dupa canal.
#
# ORDINEA SURSELOR (prima care da o limba castiga):
#   1. SURSA_GHID: ghidul TV (EIT, emisiunea de acum) are componente de subtitrare DVB (stream_content 3, tip 0x10-0x2F)
#      cu limba scrisa; numai cand toate cele cu limba stiuta spun aceeasi limba (din Python componenta nu se poate lega
#      de PID-ul pistei, deci doua limbi diferite nu spun nimic);
#   2. SURSA_SUNET: pistele de sunet ale canalului, in ordinea din PMT: prima cu limba stiuta (o pista dubla
#      "ces/slk" da prima limba); o pista cu descriere audio numai cand nu e alta (are oricum limba canalului);
#   3. SURSA_GHID_SUNET: componentele de sunet din ghidul TV (stream_content 2, 4, 6, 7), aceeasi regula, cand PMT-ul
#      nu spune limba sunetului;
#   4. SURSA_TRANSPONDER: limba celorlalte canale de pe acelasi transponder (baza canalelor de pe receptor), cate un vot
#      pe canal (prima limba a sunetului, altfel prima subtitrare DVB declarata); numai cu cel putin MIN_VOTURI voturi
#      si cel putin PROPORTIE_VOTURI din ele pentru aceeasi limba. Pachetele de canale sunt facute pe tari, deci
#      transponderul spune tara canalului mai bine decat furnizorul din lamedb ("M7", "SES": nicio limba).
#   Nimic: (None, None). Subtitrarea ramane imaginea postului (Components/HdsOcrSubtitrari.IMPLICIT_FARA_LIMBA).
#
# Limbile sunt codurile canonice ISO 639-2/T (ron, deu, fra, ces, spa ...), cum le da
# Components/HdsPisteLimbi.limbiDinText; codul modelului OCR il alege apoi HdsOcrSubtitrari (LIMBA_MODEL, VARIANTE).
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau datele (teste/test_ocr_limba_ghicita.py).
# Citirea canalului de acum (dateCanalDeAcum) e la sfarsit, cu importuri tarzii; numai memorie, fara disc si demux.

from __future__ import absolute_import

SURSA_GHID = "ghid"
SURSA_SUNET = "sunet"
SURSA_GHID_SUNET = "ghid_sunet"
SURSA_TRANSPONDER = "transponder"
SURSE = (SURSA_GHID, SURSA_SUNET, SURSA_GHID_SUNET, SURSA_TRANSPONDER)

# component_descriptor (EN 300 468, tabelul 26): stream_content 3 = subtitrari; tipurile 0x10-0x1F subtitrari DVB,
# 0x20-0x2F subtitrari DVB pentru surzi (teletextul are 0x01-0x03 si nu e poza)
CONTINUT_SUBTITRARE = 0x03
TIPURI_SUBTITRARE_DVB = frozenset(range(0x10, 0x30))
# stream_content al sunetului: MPEG-1 Layer 2, AC-3, HE-AAC, DTS
CONTINUT_SUNET = frozenset((0x02, 0x04, 0x06, 0x07))

MIN_VOTURI = 3
PROPORTIE_VOTURI = 2.0 / 3.0
MAX_CANALE_TRANSPONDER = 80     # cate canale ale transponderului se citesc din baza (un transponder are 5-30)


def _jurnal(text):
	print("[HdsOcrLimbaGhicita] %s" % text)


def _text(valoare):
	if valoare is None:
		return u""
	if isinstance(valoare, bytes):
		return valoare.decode("utf-8", "replace")
	return u"%s" % (valoare,)


def _modulLimbi():
	try:
		from Components import HdsPisteLimbi as L
		return L
	except Exception:
		try:
			import HdsPisteLimbi as L
			return L
		except Exception:
			return None


def limbi(text):
	"""Textul unei limbi ("deu", "ger", "ces/slk", "Deutsch", "und", "qaa") -> lista codurilor canonice, [] cand nu se
	stie (Components/HdsPisteLimbi.limbiDinText)."""
	L = _modulLimbi()
	if L is not None:
		try:
			return list(L.limbiDinText(_text(text)))
		except Exception:
			pass
	t = _text(text).strip().lower()
	t = t.split("/")[0].strip()
	if len(t) == 3 and t.isalpha() and not (t[0] == "q" and "a" <= t[1] <= "t") and t not in ("und", "mul", "mis",
			"zxx", "unk", "xxx"):
		return [t]
	return []


def _prima(text):
	l = limbi(text)
	return l[0] if l else None


def dinComponenteSubtitrare(componente):
	"""Componentele EIT (tag, tip, stream_content, iso639, text) -> limba subtitrarilor DVB, numai cand toate cele cu
	limba stiuta spun aceeasi; altfel None."""
	gasite = []
	for c in componente or ():
		try:
			tip, continut, iso = int(c[1]), int(c[2]), c[3]
		except (TypeError, ValueError, IndexError):
			continue
		if continut != CONTINUT_SUBTITRARE or tip not in TIPURI_SUBTITRARE_DVB:
			continue
		l = _prima(iso)
		if l and l not in gasite:
			gasite.append(l)
	return gasite[0] if len(gasite) == 1 else None


def _descriereAudio(text):
	L = _modulLimbi()
	if L is not None:
		try:
			return bool(L.esteDescriereAudio(_text(text)))
		except Exception:
			pass
	return False


def dinSunet(audio):
	"""Pistele de sunet ale canalului, in ordinea din PMT, ca in HdsPisteCanale.din_serviciu (["deu", "MPEG", 0], ...)
	sau ca text ("deu", ...) -> prima limba stiuta; descrierea audio (al treilea camp 1) numai daca nu e alta."""
	rezerva = None
	for p in audio or ():
		if isinstance(p, (list, tuple)):
			text = p[0] if p else u""
			descriere = len(p) > 2 and bool(p[2])
		else:
			text, descriere = p, False
		l = _prima(text)
		if not l:
			continue
		if descriere:
			rezerva = rezerva or l
			continue
		return l
	return rezerva


def dinComponenteSunet(componente):
	"""Componentele de sunet din EIT -> prima limba stiuta (descrierea audio, dupa textul ei, numai daca nu e alta)."""
	rezerva = None
	for c in componente or ():
		try:
			continut, iso = int(c[2]), c[3]
		except (TypeError, ValueError, IndexError):
			continue
		if continut not in CONTINUT_SUNET:
			continue
		l = _prima(iso)
		if not l:
			continue
		if _descriereAudio(c[4] if len(c) > 4 else u""):
			rezerva = rezerva or l
			continue
		return l
	return rezerva


def votCanal(rec):
	"""Inregistrarea unui alt canal de pe transponder ({"a": [[limba, fel, descriere, ...]], "d": [[limba, ...]]}) ->
	limba lui (prima limba a sunetului, altfel prima subtitrare DVB declarata), sau None."""
	if not isinstance(rec, dict):
		return None
	l = dinSunet(rec.get("a"))
	if l:
		return l
	for p in rec.get("d") or ():
		if isinstance(p, (list, tuple)) and p:
			l = _prima(p[0])
			if l:
				return l
	return None


def dinTransponder(canale, min_voturi=MIN_VOTURI, proportie=PROPORTIE_VOTURI):
	"""Inregistrarile celorlalte canale de pe transponder -> limba celor mai multe, numai cu cel putin `min_voturi`
	voturi si cel putin `proportie` din ele pentru aceeasi limba; altfel None."""
	voturi = {}
	ordine = []
	n = 0
	for rec in canale or ():
		l = votCanal(rec)
		if not l:
			continue
		n += 1
		if l not in voturi:
			voturi[l] = 0
			ordine.append(l)
		voturi[l] += 1
	if n < min_voturi:
		return None
	cea = max(ordine, key=lambda l: (voturi[l], -ordine.index(l)))
	return cea if voturi[cea] >= proportie * n else None


def ghiceste(componente=None, audio=None, transponder=None):
	"""Limba ghicita a unei subtitrari DVB fara limba -> (cod canonic, sursa) sau (None, None).
	componente: componentele EIT ale emisiunii de acum; audio: pistele de sunet ale canalului (ordinea din PMT);
	transponder: inregistrarile celorlalte canale de pe transponder, sau o functie fara argumente care le da (se
	cheama numai cand primele surse nu dau nimic)."""
	l = dinComponenteSubtitrare(componente)
	if l:
		return l, SURSA_GHID
	l = dinSunet(audio)
	if l:
		return l, SURSA_SUNET
	l = dinComponenteSunet(componente)
	if l:
		return l, SURSA_GHID_SUNET
	if transponder is not None:
		try:
			canale = transponder() if callable(transponder) else transponder
		except Exception as e:
			_jurnal("transponderul: %s" % e)
			canale = None
		l = dinTransponder(canale)
		if l:
			return l, SURSA_TRANSPONDER
	return None, None


# ------------------------------------------------------------------ canalul de acum, pe receptor (importuri tarzii)

def _cheieTp(k):
	"""Cheia unui canal "sid:ns:tsid:onid" -> "ns:tsid:onid" (hex, fara zerouri in fata), sau None."""
	if not isinstance(k, str) or k.count(":") != 3:
		return None
	try:
		p = [int(x, 16) for x in k.split(":")]
	except ValueError:
		return None
	return "%x:%x:%x" % tuple(p[1:])


def canaleDePeTransponder(cheie, b=None, maxim=MAX_CANALE_TRANSPONDER):
	"""Inregistrarile ("a", "d") celorlalte canale de pe transponderul canalului `cheie`, din baza canalelor deja
	incarcata (Components/HdsBazaCanale.baza_existenta: fara baza in memorie nu se citeste nimic de pe disc)."""
	tp = _cheieTp(cheie)
	if tp is None:
		return []
	if b is None:
		try:
			from Components import HdsBazaCanale as B
		except ImportError:
			import HdsBazaCanale as B
		b = B.baza_existenta()
	if b is None:
		return []
	rez = []
	for k in b.chei_cu(("a", "d")):
		if k == cheie or _cheieTp(k) != tp:
			continue
		rec = b.cauta(k)
		if rec:
			rez.append({"a": rec.get("a") or [], "d": rec.get("d") or []})
			if len(rez) >= maxim:
				break
	return rez


def dateCanalDeAcum():
	"""Pe receptor: {"ref", "componente", "audio", "transponder"} pentru canalul care ruleaza (numai memorie: pistele
	din nucleu, emisiunea de acum, baza canalelor deja incarcata). {} cand nu ruleaza un canal DVB."""
	try:
		import NavigationInstance
		from enigma import iServiceInformation
		nav = NavigationInstance.instance
		service = nav.getCurrentService() if nav is not None else None
		if service is None:
			return {}
		ref = nav.getCurrentlyPlayingServiceReference()
		ref = ref.toString() if ref is not None else u""
	except Exception as e:
		_jurnal("canalul de acum: %s" % e)
		return {}
	try:
		from Components import HdsPisteCanale as P
	except Exception as e:
		_jurnal("pistele canalului: %s" % e)
		return {"ref": ref}
	audio = []
	try:
		rec = P.din_serviciu(service, iServiceInformation) or {}
		audio = rec.get("a") or []
	except Exception as e:
		_jurnal("pistele de sunet: %s" % e)
	componente = []
	try:
		info = service.info()
		componente = P.componente_eit(info, iServiceInformation) if info is not None else []
	except Exception as e:
		_jurnal("ghidul TV: %s" % e)
	cheie = None
	try:
		from Components import HdsIndexCanale as X
		cheie = X.cheie_din_ref(ref)
	except Exception:
		cheie = None
	return {"ref": ref, "componente": componente, "audio": audio,
		"transponder": (lambda: canaleDePeTransponder(cheie)) if cheie else None}
