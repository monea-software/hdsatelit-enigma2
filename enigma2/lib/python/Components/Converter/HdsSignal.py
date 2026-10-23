# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
# Convertorul skinului HDSatelit (hdsatelit.com) pentru valori care se schimba in timp:
# semnal, calitate, BER, tuner, stratul DVB-T2 / DAB.
# Sursa: session.CurrentService. Se pune doar pe pagina tehnica (SecondInfoBar).
#
# Cronometrul merge DOAR cat widgetul se vede (pornit in doSuspend(0), oprit in
# doSuspend(1) si in destroy). Placa se citeste o data la 0,5 s pentru toate
# widgeturile la un loc, nu separat pentru fiecare.
from __future__ import absolute_import

from Components.Converter.Converter import Converter
from Components.Converter.Poll import Poll
from Components.Element import cached

try:
	from enigma import iPlayableService
except Exception:
	iPlayableService = None

try:
	from Components.Converter import HdsCommon as C
except Exception as _e:
	C = None
	print("[HdsSignal] HdsCommon lipseste: %s" % _e)


def _events():
	evs = set()
	for name in ("evStart", "evEnd", "evUpdatedInfo", "evTunedIn"):
		try:
			ev = getattr(iPlayableService, name, None)
		except Exception:
			ev = None
		if ev is not None:
			evs.add(ev)
	return evs


_EVENTS = _events()
_EV_START = getattr(iPlayableService, "evStart", None) if iPlayableService is not None else None
_EV_EPG = getattr(iPlayableService, "evUpdatedEventInfo", None) if iPlayableService is not None else None

# nume -> (metoda, e boolean, interval ms)
TYPES = {
	"Signal": ("_signal", False, 1000),
	"Quality": ("_quality", False, 1000),
	"Ber": ("_ber", False, 1000),
	"Tuner": ("_tuner", False, 1000),
	"Locked": ("_locked", True, 1000),
	"NoLock": ("_no_lock", True, 1000),
	# textul „Fără semnal" doar cand NoLock e adevarat, altfel gol (fereastra video din lista de canale)
	"NoLockText": ("_no_lock_text", False, 1000),
	"SignalGood": ("_signal_good", True, 1000),
	"SignalWarn": ("_signal_warn", True, 1000),
	"SignalBad": ("_signal_bad", True, 1000),
	"QualityGood": ("_quality_good", True, 1000),
	"QualityWarn": ("_quality_warn", True, 1000),
	"QualityBad": ("_quality_bad", True, 1000),
	"HasLayer": ("_has_layer", True, 2000),
	"LayerIsT2mi": ("_layer_t2mi", True, 2000),
	"LayerIsDab": ("_layer_dab", True, 2000),
	"LayerTitle": ("_layer_title", False, 2000),
	"LayerLine": ("_layer_line", False, 2000),
	# rotirea paginilor: pus o singura data pe ecran (widget fara text); value = pagina activa
	"PageTick": ("_page_tick", False, 500),
	# semnal cinstit: dB doar pe placile cu valoare reala, altfel SNR brut % din driver
	"SnrHonest": ("_snr_honest", False, 1000),
	"SnrLabel": ("_snr_label", False, 1000),
	"SnrIsDb": ("_snr_is_db", True, 1000),
	"TunerState": ("_tuner_state", False, 1000),
	# motor: pozitia din setari si miscarea (doar cand tunerul are motor)
	"RotorPosition": ("_rotor_position", False, 1000),
	"RotorMoving": ("_rotor_moving", True, 1000),
	# receptor: fisiere mici din /proc, citite rar si doar cat widgetul se vede
	"CpuLoad": ("_cpu_load", False, 2000),
	"MemFree": ("_mem_free", False, 5000),
	"Temperature": ("_temperature", False, 2000),
	"Uptime": ("_uptime", False, 30000),
	"StreamClients": ("_stream_clients", False, 5000),
	# procesorul (cpufreq, numai citire) si reteaua (ruta implicita; Internet printr-o proba pe fir separat)
	"CpuFreq": ("_cpu_freq", False, 2000),
	# pagina 6, coloana procesorului: modul si plafonul, tensiunea, timpul pe fiecare frecventa (Components/HdsProcesor,
	# numai pe imaginea HDSatelit: o citire memorata 2 s, aceeasi pentru ecranul Procesor si web; altundeva gol)
	"CpuMod": ("_cpu_mod", False, 2000),
	"CpuVolt": ("_cpu_volt", False, 2000),
	"CpuTrepte": ("_cpu_trepte", False, 2000),
	"NetIp": ("_net_ip", False, 5000),
	"NetLink": ("_net_link", False, 5000),
	"NetInternet": ("_net_internet", False, 5000),
	# pagina 4: lista CAID-urilor derulabila (CaSys,<n>,<randuri vazute>), sistemul decriptat acum in caseta
	# (CaSysAct / CaSysOn), CaIds, CaCount; EcmRow,<n> = ce spune camul (HdsCommon.ecm_rows), fara cititor si fara
	# adrese.
	# La ceas, fiindca un ECM nou nu trimite niciun eveniment de serviciu.
	"CaSys": ("_ca_sys", False, 2000),
	"CaSysAct": ("_ca_sys_act", False, 2000),
	"CaSysOn": ("_ca_sys_on", True, 2000),
	"CaIds": ("_ca_ids", False, 2000),
	"CaCount": ("_ca_count", False, 2000),
	"EcmRow": ("_ecm_row", False, 2000),
	# bara de jos: sistemul prin care se decripteaza acum, intr-o caseta (AccessBox / AccessBoxOn); celelalte ca text
	# (AccessRest,Box cat e caseta; AccessRest,NoBox = tot accesul cand nu e nimic decriptat acum)
	"AccessBox": ("_access_box", False, 2000),
	"AccessBoxOn": ("_access_box_on", True, 2000),
	"AccessRest": ("_access_rest", False, 2000),
	# pagina 5: randul scurt din banda dupa o inregistrare pusa din bara
	"EpgNote": ("_epg_note", False, 1000),
}

GOOD = 55
WARN = 30
EMPTY = ("", False, 0)

# CpuLoad: procentul e diferenta a doua citiri din /proc/stat. Prima citire se face cand se construieste ecranul. La
# prima afisare, fara o diferenta proaspata, HdsCommon.cpu_load da masurarea pazei procesorului (imaginea HDSatelit);
# fara ea, cat caseta n-a aratat inca un procent, citirea noua se face dupa numai CPU_PAS_SCURT_S de la cea dinainte,
# iar sondajul urmator vine dupa CPU_SONDAJ_SCURT_MS (de cel mult CPU_SONDAJE_SCURTE ori), nu dupa 2 s.
CPU_PAS_SCURT_S = 0.2
CPU_SONDAJ_SCURT_MS = 250
CPU_SONDAJE_SCURTE = 3

_layer_memo = {"t": -1000.0, "ref": None, "val": None}
# valorile citite din serviciu, impartite de widgeturile care se reimprospateaza la ceas (acelasi serviciu, 0,5 s);
# se tine doar dictionarul de valori Python al cititorului, niciun obiect enigma2
_rf = {"t": -1000.0, "key": None, "f": None}



class HdsSignal(Poll, Converter):
	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		self._fn = None
		self._isbool = False
		self._interval = 1000
		self._val = None
		self._opts = ()
		self._page = 0
		self._filters = ()
		self._fok = None
		self._ctx = None
		self._cpu_gol = True
		self._cpu_scurte = 0
		try:
			parts = [p.strip() for p in str(arg or "").split(",")]
			name = parts[0]
			self._opts = tuple(parts[1:])
			spec = TYPES.get(name)
			if spec is None:
				print("[HdsSignal] tip necunoscut: %r" % (arg,))
			else:
				self._fn, self._isbool, self._interval = spec
			if C is not None:
				C.refresh_lang()
				# P<n>: gol si fara citiri cat pagina n nu se vede; OnS/OnC/OnT/OnDvb/OnIp: doar la felul acela de receptie
				self._page, self._filters = C.parse_page_filters(self._opts)
				if self._page:
					C.page_subscribe(self, self._page)
				if name == "CaSys" and len(self._opts) > 1:
					C.ca_visible(self._opts[1])
				if name == "CpuLoad":
					# prima citire cat se face ecranul: la aratare e deja una cu care se face diferenta
					C.cpu_sample()
			# doar intervalul; timerul porneste cand widgetul se vede
			self.poll_interval = self._interval
		except Exception as e:
			self._fn = None
			if C is not None:
				C.log_once("HdsSignal init", e)

	# ------------------------------------------------------------ legatura cu enigma2

	def _hidden_page(self):
		"""Pagina lui nu se vede: alta pagina activa sau ecranul cu pagini ascuns (HdsCommon.page_hidden)."""
		if not self._page or C is None:
			return False
		ascunsa = getattr(C, "page_hidden", None)
		if ascunsa is not None:
			return ascunsa(self._page)
		return C.page_active() != self._page

	def doSuspend(self, suspended):
		try:
			if suspended:
				self.poll_enabled = False
				if self._fn == "_page_tick" and C is not None:
					C.page_stop()
			elif self._fn is not None:
				self._val = None
				self._fok = None
				self._ctx = None
				self._cpu_gol = True
				self._cpu_scurte = 0
				self.poll_enabled = True
				if self._fn == "_page_tick":
					if C is not None:
						C.cpu_sample()
						C.page_start(C.Reader(self.source, None))
					return
				if self._hidden_page():
					return
				Converter.changed(self, (self.CHANGED_POLL,))
		except Exception as e:
			if C is not None:
				C.log_once("doSuspend", e)

	def changed(self, what):
		try:
			kind = what[0]
			if self._fn == "_page_tick":
				self._page_events(kind, what)
				return
			if kind == self.CHANGED_SPECIFIC:
				if what[1] not in _EVENTS:
					return
				if what[1] == _EV_START and C is not None:
					C.refresh_lang()
				self._fok = None
				self._ctx = None
			self._val = None
			if self._hidden_page():
				return  # pagina lui nu se vede: iese inainte de orice citire din placa
			Converter.changed(self, what)
		except Exception as e:
			if C is not None:
				C.log_once("HdsSignal changed", e)

	def _page_events(self, kind, what):
		"""PageTick: la tic muta pagina cand ii vine randul; la zap reporneste de la pagina 1; la EPG nou reface lista."""
		if C is None or self.suspended:
			return
		if kind == self.CHANGED_POLL:
			C.page_tick(C.Reader(self.source, None))
		elif kind == self.CHANGED_SPECIFIC:
			ev = what[1]
			if ev == _EV_START:
				C.page_start(C.Reader(self.source, None))
			elif ev in _EVENTS or (ev is not None and ev == _EV_EPG):
				if ev == _EV_EPG:
					# lista ghidului se reciteste inainte de a se hotari paginile valide (convertoarele HdsInfo pot primi
					# acelasi eveniment dupa PageTick)
					C.epg_changed(what)
				C.page_tick(C.Reader(self.source, what), True)

	def _on_page(self):
		"""Chemat de HdsCommon.page_set cand pagina acestui convertor intra sau iese de pe ecran."""
		try:
			self._val = None
			if self._fn == "_cpu_load":
				# pagina intra: procentul se cere iar cu pasul scurt; pagina iese: sondajul inapoi la intervalul lui
				self._cpu_gol = True
				self._cpu_scurte = 0
				if self._hidden_page():
					self._sondaj(self._interval)
			Converter.changed(self, (self.CHANGED_ALL,))
		except Exception as e:
			if C is not None:
				C.log_once("page", e)

	def _get(self):
		v = self._val
		if v is not None:
			return v
		v = EMPTY
		try:
			if C is not None and self._fn is not None and not self._hidden_page():
				if self._filters and self._fok is None:
					self._fok = C.filter_ok(C.Reader(self.source, None), self._filters)
				res = getattr(self, self._fn)() if (self._fok or not self._filters) else None
				if self._isbool:
					v = ("", bool(res), 0)
				elif isinstance(res, tuple):
					t = C.u(res[0])
					v = (C.out(C.ltr(t)), bool(t), int(res[1]))
				else:
					t = C.u(res)
					v = (C.out(C.ltr(t)), bool(t), 0)
		except Exception as e:
			v = EMPTY
			if C is not None:
				C.log_once(self._fn or "HdsSignal", e)
		self._val = v
		return v

	@cached
	def getText(self):
		try:
			return self._get()[0]
		except Exception:
			return ""

	@cached
	def getBoolean(self):
		try:
			return self._get()[1]
		except Exception:
			return False

	@cached
	def getValue(self):
		try:
			return self._get()[2]
		except Exception:
			return 0

	text = property(getText)
	boolean = property(getBoolean)
	value = property(getValue)
	range = 100

	def destroy(self):
		try:
			self.poll_enabled = False
		except Exception:
			pass
		try:
			if C is not None:
				C.page_unsubscribe(self)
				if self._fn == "_page_tick":
					C.page_stop()
		except Exception:
			pass
		try:
			Poll.destroy(self)
		except Exception:
			pass
		try:
			self._val = None
			Converter.destroy(self)
		except Exception:
			pass

	# ------------------------------------------------------------ citiri

	def _service_ref(self):
		try:
			service = self.source.service
		except Exception:
			return None, u""
		if service is None:
			return None, u""
		sref = u""
		try:
			info = service.info()
			c = C.isi("sServiceref")
			if info and c is not None:
				sref = C.u(info.getInfoString(c))
		except Exception:
			sref = u""
		return service, sref

	def _status(self):
		service, sref = self._service_ref()
		if service is None:
			return None, sref
		return C.frontend_status(service, sref), sref

	def _pct(self, key):
		# la un post DAB+ / program DVB-T2 prin releu frontend_status da tunerul care tine purtatorul (receptie.json),
		# iar fara date None: bara ramane goala, nu „0%”
		st, sref = self._status()
		if st:
			return C.percent16(st.get(key))
		return None

	def _signal(self):
		p = self._pct("power")
		return (u"%d%%" % p, p) if p is not None else (u"", 0)

	def _quality(self):
		p = self._pct("quality")
		return (u"%d%%" % p, p) if p is not None else (u"", 0)

	def _ber(self):
		st, sref = self._status()
		b = C.ival(st or {}, "ber")
		if b < 0 or not st:
			return (u"", 0)
		return (u"%d" % b, min(b, 100))

	def _tuner(self):
		st, sref = self._status()
		n = C.ival(st or {}, "number")
		return C.tuner_name(n) if n >= 0 else u""

	def _locked(self):
		st, sref = self._status()
		return C.ival(st or {}, "lock") == 1

	def _no_lock(self):
		st, sref = self._status()
		return bool(st) and C.ival(st, "lock") == 0

	def _no_lock_text(self):
		return C.tr("no_lock") if self._no_lock() else u""

	def _level(self, key, lo, hi):
		p = self._pct(key)
		return p is not None and lo <= p < hi

	def _signal_good(self):
		return self._level("power", GOOD, 101)

	def _signal_warn(self):
		return self._level("power", WARN, GOOD)

	def _signal_bad(self):
		return self._level("power", 0, WARN)

	def _quality_good(self):
		return self._level("quality", GOOD, 101)

	def _quality_warn(self):
		return self._level("quality", WARN, GOOD)

	def _quality_bad(self):
		return self._level("quality", 0, WARN)

	# ------------------------------------------------------------ stratul DVB-T2 / DAB

	def _layer(self):
		service, sref = self._service_ref()
		if service is None or not sref:
			return None
		now = C._now()
		if _layer_memo["ref"] == sref and 0.0 <= now - _layer_memo["t"] < 1.0:
			return _layer_memo["val"]
		val = None
		try:
			val = layer_info(C.Reader(self.source, None))
		except Exception as e:
			C.log_once("layer", e)
			val = None
		_layer_memo["t"] = now
		_layer_memo["ref"] = sref
		_layer_memo["val"] = val
		return val

	def _has_layer(self):
		return bool(self._layer())

	def _layer_t2mi(self):
		l = self._layer()
		return bool(l) and l["kind"] == "t2mi"

	def _layer_dab(self):
		l = self._layer()
		return bool(l) and l["kind"] == "dab"

	def _layer_title(self):
		l = self._layer()
		return l["title"] if l else u""

	def _layer_line(self):
		l = self._layer()
		return l["line"] if l else u""

	# ------------------------------------------------------------ pagini

	def _page_tick(self):
		return (u"", C.page_active())

	# ------------------------------------------------------------ semnal cinstit

	def _kind(self):
		"""(fel receptie din transponder, tunerul, pozitia orbitala), tinut pana la urmatorul eveniment de serviciu."""
		if self._ctx is None:
			r = C.Reader(self.source, None)
			if r.info() is None:
				self._ctx = ("", -1, -1)
			else:
				tp, kk = C.reader_etp(r)
				self._ctx = (kk, C.fe_number(r), C.ival(tp, "orbital_position") if kk == "s" else -1)
		return self._ctx

	def _snr(self):
		service, sref = self._service_ref()
		if service is None:
			return None, None
		snr = C.frontend_snr(service, sref)
		return snr, C.snr_db_honest(snr, self._kind()[0])

	def _snr_honest(self):
		snr, db = self._snr()
		if db is not None:
			return (C.fmt_dec(db, 1) + u" dB", min(100, int(db)))
		raw = C.snr_raw_pct(snr) if snr else None
		if raw is None:
			return (u"", 0)
		return (u"%d%%" % raw, raw)

	def _snr_label(self):
		snr, db = self._snr()
		if db is not None:
			t = C.tr("snr")
		elif snr and C.snr_raw_pct(snr) is not None:
			t = C.tr("snr_raw")
		else:
			return u""
		return C.upper(t) if "Upper" in self._opts else t

	def _snr_is_db(self):
		return self._snr()[1] is not None

	def _tuner_state(self):
		service, sref = self._service_ref()
		if service is None:
			return u""
		key = C.TUNER_STATES.get(C.tuner_state(service, sref))
		return C.tr(key) if key else u""

	# ------------------------------------------------------------ motor

	def _rotor(self):
		kk, n, pos = self._kind()
		if kk != "s" or n < 0 or not C.has_rotor(n, pos):
			return None
		cur, moving = C.rotor_position()
		return cur, moving, pos

	def _rotor_position(self):
		"""Unde e antena: satelitul si, cu USALS pe imaginea HDSatelit, unghiul motorului. Cand setarile nu au ultima
		pozitie, dar tunerul are semnal pe satelitul cerut, antena e acolo."""
		x = self._rotor()
		if x is None:
			return u""
		cur, moving, target = x
		if moving and target >= 0:
			return C.tr("rotor_to").replace(u"{0}", C.orbital(target))
		if cur < 0 and target >= 0 and self._locked():
			cur = target
		if cur < 0:
			return C.tr("unknown")
		return C.join([C.sat_full(cur), C.usals_angle_text(self._kind()[1], cur)])

	def _rotor_moving(self):
		x = self._rotor()
		return x is not None and x[1]

	# ------------------------------------------------------------ receptor

	def _sondaj(self, ms):
		if self.poll_interval != ms:
			self.poll_interval = ms

	def _cpu_load(self):
		v = C.cpu_load(CPU_PAS_SCURT_S if self._cpu_gol else C.CPU_PAS_S)
		if v is not None:
			self._cpu_gol = False
			self._sondaj(self._interval)
			return (u"%d%%" % v, v)
		if self._cpu_gol and self._cpu_scurte < CPU_SONDAJE_SCURTE:
			self._cpu_scurte += 1
			self._sondaj(CPU_SONDAJ_SCURT_MS)
		else:
			self._sondaj(self._interval)
		return (u"", 0)

	def _mem_free(self):
		m = C.mem_free()
		if not m:
			return (u"", 0)
		free, total = m
		return (u"%d / %d MB" % (free, total), max(0, min(100, free * 100 // max(total, 1))))

	def _temperature(self):
		# proaspata din HdsProcesor (citirea de 2 s) unde exista; altfel senzorul citit de HdsCommon (memorat 20 s)
		t = C.procesor_temperatura()
		if t is None:
			t = C.temperature()
		return (u"%d °C" % t, min(100, t)) if t is not None else (u"", 0)

	def _uptime(self):
		return C.uptime_text(C.uptime_seconds())

	def _stream_clients(self):
		n = C.stream_clients()
		return (u"%d" % n, min(100, n)) if n is not None else (u"", 0)

	def _cpu_freq(self):
		return C.cpu_freq_text()

	def _cpu_mod(self):
		return C.procesor_camp("setata")

	def _cpu_volt(self):
		return C.procesor_camp("tensiune")

	def _cpu_trepte(self):
		return C.procesor_camp("trepte")

	def _net_ip(self):
		iface, ip, wifi = C.net_default()
		return ip if iface else C.tr("net_none")

	def _net_link(self):
		return C.net_link_text()

	def _net_internet(self):
		return C.net_internet_text()

	# ------------------------------------------------------------ pagina 4 si bara de jos: accesul, camul

	def _reader(self):
		"""Cititorul serviciului, cu valorile impartite intre widgeturile de la acelasi ceas (acelasi serviciu, 0,5 s)."""
		service, sref = self._service_ref()
		r = C.Reader(self.source, None)
		key = (id(self.source), sref)
		now = C._now()
		if _rf["key"] == key and _rf["f"] is not None and 0.0 <= now - _rf["t"] < 0.5:
			r.f = _rf["f"]
		else:
			_rf["t"] = now
			_rf["key"] = key
			_rf["f"] = r.f
		return r

	def _row_n(self):
		try:
			return int(self._opts[0])
		except Exception:
			return 0

	def _ca_entry(self):
		n = self._row_n()
		if n <= 0:
			return None, None
		r = self._reader()
		return r, C.ca_entry(r, n)

	def _ca_name(self, caid):
		return C.caid_name(caid) or (u"0x%04X" % caid)

	def _ca_sys(self):
		r, e = self._ca_entry()
		if e is None or e[0] == C.ecm_active(r):
			return u""
		return self._ca_name(e[0])

	def _ca_sys_act(self):
		r, e = self._ca_entry()
		if e is None or e[0] != C.ecm_active(r):
			return u""
		return self._ca_name(e[0])

	def _ca_sys_on(self):
		r, e = self._ca_entry()
		return e is not None and e[0] == C.ecm_active(r)

	def _ca_ids(self):
		r, e = self._ca_entry()
		return C.ca_ids_text(e) if e is not None else u""

	def _ca_count(self):
		return C.ca_count_text(self._reader())

	def _ecm_row(self):
		n = self._row_n()
		if n <= 0:
			return u""
		rows = C.ecm_rows(self._reader())
		return rows[n - 1] if n <= len(rows) else u""

	def _access_box(self):
		return C.active_system_short(self._reader())

	def _access_box_on(self):
		return bool(C.active_system_short(self._reader()))

	def _access_rest(self):
		r = self._reader()
		act = C.ecm_active(r)
		if "Box" in self._opts:
			# langa caseta locul e mic: Max<n> = cel mult n litere (skinul le masoara pe fontul lui); sistemele care nu
			# incap se sar, lista intreaga e pe pagina accesului
			n = 0
			for o in self._opts:
				if o.startswith("Max") and o[3:].isdigit():
					n = int(o[3:])
			return C.access_short(r, act, n) if act > 0 else u""
		if "NoBox" in self._opts:
			return u"" if act > 0 else C.access_short(r)
		return C.access_short(r, act)

	# ------------------------------------------------------------ pagina 5: randul scurt din banda

	def _epg_note(self):
		t = C.epg_note()
		if t:
			self._note_on = True
		elif getattr(self, "_note_on", False):
			# randul a expirat: textele tastelor colorate (HdsInfo EpgKey) se scriu din nou
			self._note_on = False
			C.page_refresh(C.EPG_PAGE)
		return t


def _hex_or(v):
	v = C.u(v).strip()
	if not v:
		return u""
	try:
		return u"%X" % int(v, 0) if v.lower().startswith(u"0x") else v.upper()
	except Exception:
		return v.upper()


def layer_info(r):
	"""{'kind': 't2mi'|'dab', 'title': u'', 'line': u''} sau None."""
	if r.info() is None:
		return None
	d = r.rj() or {}
	if r.is_dab():
		dab = C.rj_dict(d, "dab")
		tip = C.u(d.get("tip")).upper()
		codec_tag = r.gets("sTagCodec").upper()
		name = u"DAB" if (tip == u"DAB" or (codec_tag.startswith(u"DAB ") and not codec_tag.startswith(u"DAB+"))) else u"DAB+"
		ens = C.u(dab.get("ansamblu")) or r.gets("sDABEnsembleLabel")
		title = C.tr("layer_dab").replace(u"{0}", name)
		if ens:
			title += u": " + ens
		eid = _hex_or(dab.get("eid"))
		post = C.u(dab.get("post"))
		sid = _hex_or(dab.get("sid"))
		if not sid:
			up = r.ref()["urlpath"]
			if up:
				sid = _hex_or(up[-1])
		codec = C.u(dab.get("codec"))
		kbit = C.ival(dab, "kbit")
		pid = C.ival(C.rj_dict(d, "purtator"), "pid")
		parts = []
		if ens or eid:
			parts.append(C.join([C.upper(C.tr("ensemble")), ens, (u"(EId %s)" % eid) if eid else u""], u" "))
		if post or sid:
			parts.append(C.join([C.upper(C.tr("service")), post, (u"(SId %s)" % sid) if sid else u""], u" "))
		parts.append(C.join([codec, (u"%d kbit/s" % kbit) if kbit > 0 else u""], u" "))
		parts.append(C.u(dab.get("transport")))
		if pid >= 0:
			parts.append(u"PID %d" % pid)
		return {"kind": "dab", "title": title, "line": C.join(parts)}
	if r.is_t2mi():
		t2 = C.rj_dict(d, "t2")
		tp = r.tp() if r.kind() == "s" else r.carrier_tp()
		pid = C.ival(t2, "t2mi_pid")
		if pid < 0:
			pid = C.ival(tp, "t2mi_pid")
		plp = C.ival(t2, "plp_id")
		if plp < 0:
			plp = C.ival(tp, "t2mi_plp_id")
		net = C.u(t2.get("retea") or d.get("retea"))
		title = C.tr("layer_t2mi")
		if net:
			title += u": " + net
		guard = C.TER_GUARD.get(C.ival(t2, "guard_interval"), u"")
		radio = C.join([
			C.TER_TMODE.get(C.ival(t2, "transmission_mode"), u""),
			C.TER_CONST.get(C.ival(t2, "constellation"), u""),
			C.TER_RATE.get(C.ival(t2, "code_rate"), u""),
			(u"GI " + guard) if guard else u"",
		], u" ")
		parts = [
			(u"%s %d" % (C.tr("t2mi_pid"), pid)) if pid >= 0 else u"",
			(u"%s %d" % (C.tr("plp"), plp)) if plp >= 0 else u"",
			radio,
			C.bandwidth_text(t2),
		]
		return {"kind": "t2mi", "title": title, "line": C.join(parts)}
	return None
