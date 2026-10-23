# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRadioDate.py: datele postului de radio care merge, aceleasi pentru ecranul radio de pe televizor
# (Screens/HdsEcranRadio.py) si pentru pagina web (Plugins/Extensions/HdsWebControl/radio_web.py).
#
# De unde vin:
# - numele, furnizorul, numarul din lista: serviciul si referinta lui;
# - emisiunea de acum din EIT (info.getEvent(0)), urmatoarele din cache-ul EPG (lookupEvent „IBDT” pe 6 ore);
# - textul radio, piesa (RT+) si semnul RaSS: decodorul RDS al nucleului (service.rdsDecoder());
# - codecul, limba si pistele din PMT; debitul, esantionarea si modul (stereo, joint stereo, mono) din analizorul
#   fluxului (Components/HdsRadioAnaliza.py), cand merge;
# - satelitul, frecventa, polarizarea, SR, FEC, sistemul si modulatia: transponderul serviciului, cu functiile comune
#   ale skinului (Components/Converter/HdsCommon.py), iar fara tuner (acordare esuata, emulator) transponderul din
#   lista de canale;
# - semnalul: tunerul (calitatea in procente si raportul semnal/zgomot in dB).
# Clasificarea „e radio” e cea a barei (HdsInfo: tip de serviciu 2 sau 0x0A, DAB, flux doar audio, inregistrare fara
# video); daca modulul barei nu se poate folosi, ramane regula tipului de serviciu.
#
# Toate functiile ruleaza pe firul enigma2 si sunt scurte (cateva apeluri catre serviciu, un lookupEvent). Nicio
# functie publica nu arunca: fara date intorc campuri goale.

import time

RADIO_STYPES = (2, 10)
EPG_ORE = 6


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _u(s):
	if s is None:
		return u""
	if isinstance(s, bytes):
		return s.decode("utf-8", "replace")
	return u"%s" % s


def _curata_nume(nume):
	# semnele de evidentiere DVB (0x86, 0x87) din numele venite de la emitator nu se arata
	return _u(nume).replace(u"\u0086", u"").replace(u"\u0087", u"").strip()


def _C():
	try:
		from Components.Converter import HdsCommon
		return HdsCommon
	except Exception:
		return None


class _Sursa(object):
	"""Ce asteapta HdsCommon.Reader de la o sursa: serviciul si referinta."""
	__slots__ = ("service", "serviceref")

	def __init__(self, service, serviceref):
		self.service = service
		self.serviceref = serviceref


def tip_serviciu(ref_text):
	"""Tipul serviciului din referinta DVB (al treilea camp, in hex) sau -1."""
	f = _u(ref_text).split(u":")
	if len(f) > 2:
		try:
			return int(f[2], 16)
		except ValueError:
			return -1
	return -1


def este_radio_ref(ref_text):
	"""Numai dupa referinta: tip de serviciu 2 sau 0x0A (ca lista de radio a enigma2)."""
	return tip_serviciu(ref_text) in RADIO_STYPES


def este_radio(service, ref_text):
	"""Clasificarea barei (HdsInfo._radio_calc) pe serviciul care merge; fara ea, dupa referinta."""
	if este_radio_ref(ref_text):
		return True
	C = _C()
	if C is None or service is None:
		return False
	try:
		from Components.Converter.HdsInfo import HdsInfo
		r = C.Reader(_Sursa(service, None), None)
		return bool(HdsInfo._radio_calc(None, r))
	except Exception:
		return False


def _cheie_ref(text):
	return u":".join(_u(text).split(u":")[:10]).lower()


def ref_curenta(session):
	"""(referinta, text) a serviciului care merge. La evStart, Navigation.playService n-a pus inca referinta noua
	(currentlyPlayingServiceReference se schimba dupa ce nucleul porneste serviciul, iar evStart vine in timpul
	pornirii), deci textul vine din serviciul insusi (sServiceref); referinta navigatiei se foloseste cand e aceeasi
	(are numarul din lista)."""
	try:
		ref = session.nav.getCurrentlyPlayingServiceReference()
	except Exception:
		ref = None
	text_nav = _u(ref.toString()) if ref is not None else u""
	text = u""
	try:
		service = session.nav.getCurrentService()
		info = service.info() if service is not None else None
		if info is not None:
			text = _info_text(info, "sServiceref")
	except Exception:
		text = u""
	if text and _cheie_ref(text) != _cheie_ref(text_nav):
		try:
			from enigma import eServiceReference
			return eServiceReference(str(text)), text
		except Exception:
			return None, text
	return ref, (text_nav or text)


def nume_serviciu(ref):
	if ref is None:
		return u""
	try:
		from ServiceReference import ServiceReference
		return _curata_nume(ServiceReference(ref).getServiceName())
	except Exception:
		return u""


def numar_in_lista(ref):
	"""Numarul postului in lista din care a pornit: din referinta, pe imaginile care il tin acolo (getChannelNum);
	in enigma2-ul imaginii referinta nu are numar, deci locul in buchetul listei (HdsInfo.numar_in_lista). 0 = fara."""
	fn = getattr(ref, "getChannelNum", None)
	if fn is not None:
		try:
			return int(fn() or 0)
		except Exception:
			return 0
	if ref is None:
		return 0
	try:
		from Components.Converter.HdsInfo import numar_in_lista as numar
	except ImportError:
		return 0
	return numar(ref)


def _eveniment(info, n):
	try:
		ev = info.getEvent(n)
	except Exception:
		return None
	if not ev:
		return None
	try:
		titlu = _u(ev.getEventName()).strip()
		inceput = int(ev.getBeginTime() or 0)
		durata = int(ev.getDuration() or 0)
	except Exception:
		return None
	if not titlu:
		return None
	return {"inceput": inceput, "durata": durata, "titlu": titlu[:160]}


def _epg_cache(ref_text, ore=EPG_ORE):
	"""[(inceput, durata, titlu)] din cache-ul EPG, de acum inainte, in ordinea timpului."""
	f = _u(ref_text).split(u":")
	if len(f) < 10 or f[0] != u"1":
		return []
	cheie = u":".join(f[:10]) + u":"
	try:
		from enigma import eEPGCache
		lst = eEPGCache.getInstance().lookupEvent(["IBDT", (str(cheie), 0, -1, int(ore * 60))])
	except Exception:
		return []
	rez = []
	vazute = set()
	for e in (lst or [])[:40]:
		try:
			eid = int(e[0])
			inceput = int(e[1])
			durata = int(e[2])
			titlu = _u(e[3]).strip()
		except Exception:
			continue
		if inceput <= 0 or not titlu or eid in vazute:
			continue
		vazute.add(eid)
		rez.append({"inceput": inceput, "durata": max(0, durata), "titlu": titlu[:160]})
	rez.sort(key=lambda x: x["inceput"])
	return rez


def epg(info, ref_text, cate, acum=None):
	"""{"acum": {...} sau None, "urmatoare": [...]} sau None cand postul nu transmite nimic."""
	if acum is None:
		acum = time.time()
	cur = _eveniment(info, 0) if info is not None else None
	din_cache = _epg_cache(ref_text)
	if cur is None:
		for e in din_cache:
			if e["inceput"] <= acum < e["inceput"] + e["durata"]:
				cur = e
				break
	urm = []
	prag = (cur["inceput"] + max(cur["durata"], 1) - 1) if cur else acum
	for e in din_cache:
		if e["inceput"] > prag and len(urm) < cate:
			urm.append(e)
	if not urm and info is not None:
		e = _eveniment(info, 1)
		if e is not None and e["inceput"] > prag:
			urm.append(e)
	if cur is None and not urm:
		return None
	if cur is not None:
		cur = dict(cur)
		sfarsit = cur["inceput"] + cur["durata"]
		if cur["durata"] > 0 and cur["inceput"] <= acum <= sfarsit:
			cur["progres"] = int(100 * (acum - cur["inceput"]) / cur["durata"])
			cur["ramas_min"] = int((sfarsit - acum + 59) // 60)
		else:
			cur["progres"] = -1
			cur["ramas_min"] = -1
	return {"acum": cur, "urmatoare": urm}


def rds(service, session=None):
	"""{"text": RadioText, "piesa": RT+ (artistul si titlul), "rass": True cand postul are pagini RaSS}.
	Textele trec prin Components/HdsRdsText.py: se iau numai dupa ce decodorul RDS a anuntat un mesaj bun pentru
	serviciul care merge (la AAC nu vine niciunul) si numai daca sunt text valid, decodat in setul lor de caractere."""
	rez = {"text": u"", "piesa": u"", "rass": False}
	try:
		dec = service.rdsDecoder() if service is not None else None
	except Exception:
		dec = None
	if not dec:
		return rez
	try:
		from Components import HdsRdsText as T
		if session is not None:
			T.urmareste(getattr(session, "nav", None))
		rez["text"] = T.text_decodor(dec, T.TEXT)
		rez["piesa"] = T.text_decodor(dec, T.PIESA)
	except Exception:
		pass
	try:
		masca = dec.getRassInteractiveMask()
		rez["rass"] = bool(masca and masca[0] & 1)
	except Exception:
		pass
	return rez


def _info_int(info, nume):
	try:
		from enigma import iServiceInformation
		return int(info.getInfo(getattr(iServiceInformation, nume)))
	except Exception:
		return -1


def _info_text(info, nume):
	try:
		from enigma import iServiceInformation
		return _u(info.getInfoString(getattr(iServiceInformation, nume)))
	except Exception:
		return u""


def pid_audio(service):
	"""PID-ul pistei audio care merge (sAudioPID, altfel pista curenta), sau -1."""
	try:
		info = service.info()
	except Exception:
		return -1
	pid = _info_int(info, "sAudioPID") if info else -1
	if pid > 0:
		return pid
	C = _C()
	if C is None:
		return -1
	try:
		randuri, cur = C.Reader(_Sursa(service, None), None).track_list()
		if randuri:
			return int(randuri[cur if cur >= 0 else 0][2])
	except Exception:
		pass
	return -1


def demux_serviciu(service):
	"""Numarul demultiplexorului de date al serviciului care merge (iStreamableService.getStreamingData()["demux"],
	lib/service/servicedvb.cpp), sau None cand imaginea nu il da (fisier, flux, serviciu fara PMT inca)."""
	try:
		s = service.stream()
		d = s and s.getStreamingData()
	except Exception:
		return None
	if isinstance(d, dict):
		n = d.get("demux")
		if isinstance(n, int) and 0 <= n < 16:
			return n
	return None


def numar_tuner(service):
	try:
		from enigma import iFrontendInformation
		fe = service.frontendInfo()
		return int(fe.getFrontendInfo(iFrontendInformation.frontendNumber)) if fe else -1
	except Exception:
		return -1


def _semnal(service, ref_text, C):
	"""Semnalul (puterea, „putere”) si calitatea (raportul semnal / zgomot, „calitate”) in procente, ca barele SEMNAL si
	CALITATE de pe bara de la TV (Converter/HdsSignal: Signal = power, Quality = quality); „procent” ramane calitatea,
	pentru cine il citea inainte. La un post DAB+ / program DVB-T2 prin releu (flux local, fara tuner propriu) valorile
	sunt ale tunerului care tine purtatorul (HdsCommon.frontend_status, din receptie.json): „purtator” e True si
	„tuner” e litera lui; fara citirea controlorului totul ramane None („flux”: serviciul nu are tuner propriu;
	„releu”: are totusi un purtator, deci lipsesc datele, nu semnalul)."""
	rez = {"procent": None, "putere": None, "calitate": None, "db": None, "blocat": None, "purtator": False,
		"tuner": u"", "flux": False, "releu": False}
	if service is None or C is None:
		return rez
	try:
		rez["flux"] = bool(ref_text) and C.ref_din_flux(ref_text)
		rez["releu"] = rez["flux"] and C.flux_releu(ref_text)
	except Exception:
		rez["flux"] = False
	try:
		st = C.frontend_status(service, ref_text) or {}
	except Exception:
		st = {}
	q = C.percent16(st.get("quality")) if st.get("quality") is not None else None
	p = C.percent16(st.get("power")) if st.get("power") is not None else None
	rez["procent"] = q
	rez["calitate"] = q
	rez["putere"] = p
	if st.get("lock") is not None and st.get("lock") >= 0:
		rez["blocat"] = bool(st.get("lock"))
	if st.get("purtator"):
		rez["purtator"] = True
		n = st.get("number")
		if isinstance(n, int) and 0 <= n <= 25:
			rez["tuner"] = u"%c" % (65 + n)
	if rez["flux"]:
		return rez               # enigma2 da 0 dB la un canal fara tuner
	try:
		from enigma import iFrontendInformation
		fe = service.frontendInfo()
		c = getattr(iFrontendInformation, "signalQualitydB", None)
		if fe and c is not None:
			v = int(fe.getFrontendInfo(c))
			if 0 < v < 10000:
				rez["db"] = v / 100.0
	except Exception:
		pass
	return rez


def _receptie(r, ref_text, C):
	rez = {"fel": "", "satelit": u"", "pozitie": u"", "frecventa": u"", "polarizare": u"", "sr": u"", "fec": u"",
		"sistem": u"", "modulatie": u"", "din_lista": False}
	if C is None:
		return rez
	try:
		tp, kk = C.reader_etp(r) if r is not None else ({}, "")
	except Exception:
		tp, kk = {}, ""
	if not tp and ref_text:
		try:
			tp = C.static_tp(ref_text) or {}
			kk = C.tp_kind(tp)
			rez["din_lista"] = bool(tp)
		except Exception:
			tp, kk = {}, ""
	if not tp or not kk:
		return rez
	rez["fel"] = kk
	try:
		if kk == "s":
			pos = C.ival(tp, "orbital_position")
			if pos >= 0:
				rez["satelit"] = C.sat_full(pos)
				rez["pozitie"] = C.orbital(pos)
			cheie = C.SAT_POL_KEY.get(C.ival(tp, "polarization"))
			rez["polarizare"] = C.SAT_POL.get(C.ival(tp, "polarization"), u"")
			rez["polarizare_text"] = C.tr(cheie) if cheie else u""
		elif kk == "c":
			rez["satelit"] = C.tr("rec_cable")
		elif kk == "t":
			rez["satelit"] = C.tr("rec_terr")
		mhz = C.to_mhz(tp.get("frequency"))
		rez["frecventa"] = (C.fmt_mhz(mhz) + u" MHz") if mhz is not None else u""
		if kk in ("s", "c"):
			rez["sr"] = C.symbol_rate(tp)
		if kk in ("s", "c", "t"):
			rez["fec"] = C.fec_text(tp, kk)
		rez["sistem"] = C.system_text(tp, kk)
		rez["modulatie"] = C.modulation_text(tp, kk)
	except Exception:
		pass
	return rez


def _sunet(r, analiza, C):
	rez = {"codec": u"", "limba": u"", "piste": 0, "debit": 0, "debit_masurat": False, "esantionare": 0, "mod": u"",
		"canale": 0, "lfe": False}
	if r is not None and C is not None:
		try:
			n, codec, limba = r.audio()
			rez["piste"] = int(n or 0)
			rez["codec"] = _u(codec)
			rez["limba"] = _u(limba)
		except Exception:
			pass
	if analiza:
		# felul sunetului il stie analizorul pe orice format (MPEG, AAC, AC-3, E-AC-3, DTS, PCM)
		if analiza.get("codec") and analiza.get("format"):
			rez["codec"] = analiza["codec"]
		for cheie in ("debit", "esantionare", "mod", "canale", "lfe"):
			if analiza.get(cheie):
				rez[cheie] = analiza[cheie]
		rez["debit_masurat"] = bool(analiza.get("format") == "aac" and analiza.get("debit"))
	return rez


def date(session, cate_epg=3, analiza=None, acum=None):
	"""Toate datele postului care merge, ca dictionar de valori Python (si pentru JSON)."""
	ref, ref_text = ref_curenta(session)
	try:
		service = session.nav.getCurrentService()
	except Exception:
		service = None
	try:
		info = service.info() if service is not None else None
	except Exception:
		info = None
	C = _C()
	r = None
	if C is not None and service is not None:
		try:
			r = C.Reader(_Sursa(service, ref), None)
		except Exception:
			r = None
	nume = nume_serviciu(ref)
	d = {
		"ref": ref_text,
		"radio": bool(ref_text) and este_radio(service, ref_text),
		"nume": nume,
		"furnizor": _info_text(info, "sProvider").strip() if info is not None else u"",
		"numar": numar_in_lista(ref),
		"epg": epg(info, ref_text, cate_epg, acum),
		"rds": rds(service, session),
		"receptie": _receptie(r, ref_text, C),
		"semnal": _semnal(service, ref_text, C),
		"sunet": _sunet(r, analiza, C),
		"acces": None,
		"analiza": analiza or {},
	}
	if r is not None:
		try:
			d["acces"] = r.acces()
		except Exception:
			pass
	return d


def rapid(d, session, analiza=None, acum=None, cu_rds=False):
	"""Partea care se schimba des, peste datele `d` de la ultimul date(): semnalul, sunetul din analizor si cat a
	trecut din emisiunea de acum; cu cu_rds=True si textul radio. Fara cautari in EPG (acelea le face date())."""
	if acum is None:
		acum = time.time()
	d = dict(d)
	try:
		service = session.nav.getCurrentService()
	except Exception:
		service = None
	C = _C()
	r = None
	if C is not None and service is not None:
		try:
			r = C.Reader(_Sursa(service, None), None)
		except Exception:
			r = None
	d["semnal"] = _semnal(service, d.get("ref", u""), C)
	d["sunet"] = _sunet(r, analiza, C)
	d["analiza"] = analiza or {}
	if cu_rds:
		d["rds"] = rds(service, session)
	ep = d.get("epg")
	cur = ep.get("acum") if ep else None
	if cur:
		cur = dict(cur)
		sfarsit = cur["inceput"] + cur["durata"]
		if cur["durata"] > 0 and cur["inceput"] <= acum <= sfarsit:
			cur["progres"] = int(100 * (acum - cur["inceput"]) / cur["durata"])
			cur["ramas_min"] = int((sfarsit - acum + 59) // 60)
		else:
			cur["progres"] = -1
			cur["ramas_min"] = -1
		d["epg"] = dict(ep, acum=cur)
	return d


def semnal_acum(session):
	"""Semnalul canalului care merge, scurt, pentru pagina de start din web (GET /api/statusinfo): {"putere",
	"calitate"} in procente sau None, „text” (randul de langa bare, ca pe ecranul radio: tunerul purtatorului, sistemul,
	„fără semnal” / „fără date de la tuner”) si „slab”. Aceleasi valori ca barele SEMNAL si CALITATE de pe televizor;
	la un post DAB+ / program DVB-T2 prin releu, ale tunerului care tine purtatorul. Fara EPG si fara RDS."""
	ref, ref_text = ref_curenta(session)
	try:
		service = session.nav.getCurrentService()
	except Exception:
		service = None
	rez = {"putere": None, "calitate": None, "text": u"", "slab": False}
	C = _C()
	if service is None or C is None or not ref_text:
		return rez
	# redarea unui fisier (inregistrare, film): nu e semnal de tuner; nimic, ca pe televizor (skinul acopera casetele
	# SEMNAL / CALITATE cu HdsInfo IsFile). Timeshift-ul ramane pe canal, cu semnalul tunerului.
	if este_fisier(ref_text):
		return rez
	try:
		r = C.Reader(_Sursa(service, ref), None)
	except Exception:
		r = None
	d = {"receptie": _receptie(r, ref_text, C), "semnal": _semnal(service, ref_text, C)}
	rez["putere"], rez["calitate"] = procente_semnal(d)
	rez["text"] = text_semnal(d)
	rez["slab"] = bool(semnal_slab(d))
	return rez


def este_fisier(ref_text):
	"""Referinta unui fisier de pe disc (inregistrare, film): calea, in campul 11, incepe cu /."""
	f = _u(ref_text).split(u":")
	return len(f) > 10 and f[10].startswith(u"/")


def este_post_radio(service, ref_text):
	"""Un post de radio pentru ecranul radio: DVB (tip de serviciu 2 sau 0x0A), DAB sau flux doar audio, dupa
	clasificarea barei; nu fisierele si inregistrarile de pe disc (acelea le reda playerul lor)."""
	if este_fisier(ref_text):
		return False
	return este_radio(service, ref_text)


# ---------------------------------------------------------------- textele de pe ecran (aceleasi si in web)

def N_(text):
	"""Marcaj pentru xgettext, fara efect: textul se traduce la folosire."""
	return text


# „joint stereo” e un fel de codare a sunetului stereo; pentru om e tot stereo
MODURI_TEXT = {
	"stereo": N_("stereo"),
	"joint_stereo": N_("stereo"),
	"dual": N_("două canale"),
	"mono": N_("mono"),
}


def _numar(x, zecimale=1):
	return (u"%%.%df" % zecimale % x).replace(u".", u",")


def text_nume(d):
	if d.get("nume"):
		return d["nume"]
	rec = d.get("receptie") or {}
	extra = u" ".join(x for x in (rec.get("frecventa"), rec.get("polarizare")) if x)
	return (_t("Post fără nume") + (u", " + extra if extra else u""))


def text_detalii(d):
	"""Furnizorul si numarul din lista (satelitul are randul lui, jos: text_satelit)."""
	parti = []
	if d.get("furnizor"):
		parti.append(d["furnizor"])
	if d.get("numar"):
		parti.append(_t("canalul %d") % d["numar"])
	return u", ".join(parti)


def text_satelit(d):
	"""Numele satelitului cu pozitia (sau cablu / terestru), scris o singura data pe ecran."""
	rec = d.get("receptie") or {}
	return rec.get("satelit") or rec.get("pozitie") or u""


def text_sunet(d):
	"""MP2, 256 kbit/s, 48 kHz, stereo, limba ron."""
	s = d.get("sunet") or {}
	parti = []
	if s.get("codec"):
		parti.append(s["codec"])
	if s.get("debit"):
		parti.append((u"%d kbit/s" % s["debit"]) if not s.get("debit_masurat") else (_t("cam %d kbit/s") % s["debit"]))
	if s.get("esantionare"):
		k = s["esantionare"] / 1000.0
		parti.append((u"%d kHz" % k) if k == int(k) else (_numar(k) + u" kHz"))
	if s.get("mod"):
		parti.append(_t(MODURI_TEXT.get(s["mod"], s["mod"])))
	elif s.get("canale"):
		if s.get("lfe") and s["canale"] > 1:
			parti.append(_t("%d.1 canale") % s["canale"])
		else:
			parti.append({1: _t("mono"), 2: _t("stereo")}.get(s["canale"], _t("%d canale") % s["canale"]))
	if s.get("limba"):
		parti.append(_t("limba %s") % s["limba"])
	if s.get("piste", 0) > 1:
		parti.append(_t("%d piste de sunet") % s["piste"])
	return u", ".join(parti)


def text_transponder(d):
	"""11623 MHz, verticală, SR 27500, FEC 3/4 (polarizarea in cuvinte, in limba ecranelor; SR si FEC sunt
	prescurtarile folosite peste tot pentru rata de simboluri si corectia erorilor)."""
	rec = d.get("receptie") or {}
	parti = []
	if rec.get("frecventa"):
		parti.append(rec["frecventa"])
	pol = rec.get("polarizare_text") or rec.get("polarizare")
	if pol:
		parti.append(pol.lower() if rec.get("polarizare_text") else pol)
	if rec.get("sr"):
		parti.append(u"SR %s" % rec["sr"])
	if rec.get("fec"):
		parti.append(u"FEC %s" % rec["fec"])
	return u", ".join(parti)


def text_semnal(d):
	"""Randul de langa barele SEMNAL si CALITATE: „DVB-S2 8PSK, 12,4 dB, liber” (procentele le arata barele).
	Fara semnal: „fără semnal”; fara tuner (acordare esuata, emulator): „fără date de la tuner”. La un post DAB+ /
	program DVB-T2 prin releu: „Tunerul A, DVB-S QPSK, liber” (tunerul care tine purtatorul), iar cand controlorul nu a
	dat inca semnalul, „fără date de la tuner” (niciodata „fără semnal” din zerourile canalului fara tuner)."""
	rec = d.get("receptie") or {}
	sem = d.get("semnal") or {}
	parti = []
	if sem.get("purtator") and sem.get("tuner"):
		parti.append(_t("Tunerul %s") % sem["tuner"])
	if rec.get("sistem"):
		parti.append(rec["sistem"])
	if sem.get("blocat") is False:
		parti.append(_t("fără semnal"))
	elif sem.get("db"):
		parti.append(u"%s dB" % _numar(sem["db"]))
	if sem.get("procent") is None and sem.get("putere") is None and (rec.get("din_lista") or sem.get("releu")):
		parti.append(_t("fără date de la tuner"))
	if d.get("acces") == "criptat":
		parti.append(_t("criptat"))
	elif d.get("acces") == "fta":
		parti.append(_t("liber"))
	return u", ".join(parti)


def etichete_semnal():
	"""Cuvintele barelor SEMNAL si CALITATE, aceleasi ca pe bara de la TV (Converter/HdsCommon, cheile „signal” si
	„quality”, cu majuscule)."""
	C = _C()
	if C is not None:
		try:
			if hasattr(C, "refresh_lang"):
				C.refresh_lang()
			return C.upper(C.tr("signal")), C.upper(C.tr("quality"))
		except Exception:
			pass
	return _t("Semnal").upper(), _t("Calitate").upper()


def procente_semnal(d):
	"""(semnalul, calitatea) in procente 0-100, ca barele de la TV; None unde tunerul nu da valoarea."""
	sem = d.get("semnal") or {}

	def _p(v):
		try:
			return max(0, min(100, int(v))) if v is not None else None
		except (TypeError, ValueError):
			return None
	return _p(sem.get("putere")), _p(sem.get("calitate", sem.get("procent")))


def semnal_slab(d):
	sem = d.get("semnal") or {}
	return sem.get("blocat") is False or (sem.get("procent") is not None and sem["procent"] < 30)


def ora(t):
	try:
		return time.strftime("%H:%M", time.localtime(int(t)))
	except Exception:
		return u""


def text_ramas(ev):
	if not ev or ev.get("ramas_min", -1) < 0:
		return u""
	m = ev["ramas_min"]
	if m == 1:
		return _t("mai este un minut")
	return _t("mai sunt %d min") % m


def text_urmatoare(ev):
	return u"%s  %s" % (ora(ev["inceput"]), ev["titlu"])


def text_bare(analiza, fel_vizualizator):
	"""De ce nu sunt bare, intr-o fraza simpla; gol cand barele merg (pe orice format de sunet) sau vizualizatorul e
	oprit."""
	if fel_vizualizator == "oprit":
		return u""
	stare = (analiza or {}).get("stare")
	if stare in ("bare", "mp2"):
		return u""
	if stare in ("fara-bare", "aac-fara-bare", "necunoscut"):
		return _t("La acest post nu se pot arăta barele.")
	if stare == "fara-date":
		return _t("Barele nu sunt disponibile pe acest post.")
	if stare == "asteapta":
		return _t("Se citește sunetul postului...")
	return u""


def text_bare_detaliu(analiza, fel_vizualizator):
	"""Randul mic de sub text_bare. Barele merg pe orice format de sunet, deci nu mai e nimic de explicat: gol."""
	return u""


# ---------------------------------------------------------------- postul urmator din lista radio


def vecin(ref_text, directie, config=None):
	"""Referinta postului urmator (directie 1) sau anterior (-1) din lista radio aleasa ultima data
	(config.radio.lastroot), sarind peste separatoare si dosare, cu intoarcere la capat. None daca nu se poate."""
	try:
		if config is None:
			from Components.config import config
		from enigma import eServiceReference, eServiceCenter
		radacini = [x for x in config.radio.lastroot.value.split(";") if x.strip()]
		if not radacini:
			return None
		radacina = eServiceReference(radacini[-1])
		lista = eServiceCenter.getInstance().list(radacina)
		if lista is None:
			return None
		ordonat = bool(radacina.flags & eServiceReference.sort1)
		refs = [x for x in (lista.getContent("R", ordonat) or []) if not (x.flags & (eServiceReference.isMarker | eServiceReference.isDirectory))]
	except Exception as e:
		print("[HdsRadio] lista radio: %s" % e)
		return None
	if not refs:
		return None
	cheie = u":".join(_u(ref_text).split(u":")[:10])
	chei = [u":".join(_u(x.toString()).split(u":")[:10]) for x in refs]
	try:
		i = chei.index(cheie)
	except ValueError:
		return refs[0]
	return refs[(i + directie) % len(refs)]
