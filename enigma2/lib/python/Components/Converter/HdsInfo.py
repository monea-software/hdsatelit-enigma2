# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
# Convertorul skinului HDSatelit (hdsatelit.com): datele tehnice ale serviciului redat.
# Sursa: session.CurrentService. Argument: "Tip", "Tip,optiune" sau "Label,cheie[,Upper]".
# Tipurile de timp (Remaining, Elapsed, Duration) au sursa session.Event_Now.
# Lista tipurilor si exemplele: CONTRACT-CONVERTOR.md.
#
# Fara cronometru: se recalculeaza doar la evenimentele de serviciu care conteaza
# pentru tipul respectiv. Singura exceptie sunt tipurile de timp: un cronometru al lor,
# creat la prima aratare, pornit doar cat se vad, cu o trezire la schimbarea minutului.
# Constructorul si toate proprietatile nu arunca exceptii.
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
	print("[HdsInfo] HdsCommon lipseste: %s" % _e)

EV_ALL = 1      # evStart, evEnd: totul
EV_INFO = 2     # evUpdatedInfo: PMT, transponder, piste
EV_VIDEO = 4    # schimbari video
EV_HBB = 8      # HbbTV
EV_START = 16   # doar evStart (limba)
EV_EPG = 32     # evUpdatedEventInfo: emisiunea curenta si urmatoarele


def _event_bits():
	bits = {}
	if iPlayableService is None:
		return bits
	table = (
		("evStart", EV_ALL | EV_INFO | EV_VIDEO | EV_HBB | EV_START),
		("evEnd", EV_ALL | EV_INFO | EV_VIDEO | EV_HBB),
		("evUpdatedInfo", EV_INFO | EV_VIDEO | EV_HBB),
		("evVideoSizeChanged", EV_VIDEO),
		("evVideoFramerateChanged", EV_VIDEO),
		("evVideoProgressiveChanged", EV_VIDEO),
		("evVideoGammaChanged", EV_VIDEO),
		("evHBBTVInfo", EV_HBB),
		("evUpdatedEventInfo", EV_EPG),
	)
	for name, b in table:
		try:
			ev = getattr(iPlayableService, name, None)
		except Exception:
			ev = None
		if ev is not None:
			bits[ev] = bits.get(ev, 0) | b
	return bits


_EVBITS = _event_bits()


def _cam_events():
	"""Evenimentele care conteaza pentru CAM: valoare -> nume."""
	names = {}
	if iPlayableService is None:
		return names
	for name in ("evStart", "evEnd", "evVideoSizeChanged"):
		try:
			ev = getattr(iPlayableService, name, None)
		except Exception:
			ev = None
		if ev is not None:
			names[ev] = name
	return names


_CAMEV = _cam_events()


def _pagina_ascunsa(page):
	"""Pagina `page` nu se vede: nu e cea activa sau ecranul cu pagini e ascuns (HdsCommon.page_hidden); cu un HdsCommon
	mai vechi, numai pagina activa."""
	ascunsa = getattr(C, "page_hidden", None)
	if ascunsa is not None:
		return ascunsa(page)
	return C.page_active() != page


# ---------------------------------------------------------------- evEnd amanat pentru numarul canalului
# Numarul din lista de canale (numar_in_lista) citeste buchetul, zeci de ms pe receptor. La o schimbare de canal evEnd
# (serviciul vechi) si evStart (cel nou) vin in acelasi apel (Navigation.playService), inainte de pornirea decodorului,
# iar ecranul nu se deseneaza intre ele: numarul calculat la evEnd nu se vede niciodata. De aceea convertoarele care
# il folosesc lasa evEnd pe un ceas de 0 ms (dupa ce apelul s-a terminat si decodorul a pornit); daca intre timp a venit
# alt eveniment (evStart), evEnd nu se mai trimite. Fara evStart (oprirea serviciului), widgetul primeste evEnd ca
# inainte, la urmatorul pas al buclei.
try:
	_EV_END = iPlayableService.evEnd if iPlayableService is not None else None
except Exception:
	_EV_END = None

_amanate = {}               # id(convertor) -> (convertor, what-ul evEnd amanat, cititorul oprit)
_ceas_amanare = [None]


class _InfoOprita(object):
	"""In locul informatiei serviciului de la evEnd: numai numele, ca text."""

	def __init__(self, nume):
		self._nume = nume

	def getName(self):
		return self._nume


class _CititorOprit(object):
	"""Ce le trebuie numarului si numelui din serviciul de la evEnd, citit pe loc (ieftin) si tinut numai ca text
	Python: un obiect enigma2 tinut pana la ceas ar tine viu serviciul vechi (si decodorul lui) peste pornirea celui
	nou. Numarul insusi (citirea buchetului) se afla abia la ceas, daca mai trebuie."""

	def __init__(self, r):
		self.source = r.source
		self.f = {}
		self._info = None
		self._sref = u""
		i = r.info()
		if i is not None:
			try:
				nume = i.getName()
			except Exception:
				nume = u""
			self._info = _InfoOprita(nume)
			self._sref = r.sref()

	def info(self):
		return self._info

	def sref(self):
		return self._sref

	def _memo(self, key, fn):
		f = self.f
		if key in f:
			return f[key]
		try:
			v = fn()
		except Exception as e:
			if C is not None:
				C.log_once(key, e)
			v = None
		f[key] = v
		return v


def _amana_end(conv, what):
	"""Pune evEnd-ul convertorului pe ceasul de 0 ms, cu valorile serviciului luate acum. False (si nimic amanat)
	cand ceasul enigma2 nu exista sau valorile nu se pot lua."""
	if C is None:
		return False
	ceas = _ceas_amanare[0]
	if ceas is None:
		try:
			from enigma import eTimer
			ceas = eTimer()
			ceas.callback.append(_la_ceas_amanare)
		except Exception:
			return False
		_ceas_amanare[0] = ceas
	try:
		r = C.Reader(conv.source, what)
		# acelasi cititor oprit pentru toate convertoarele aceluiasi evEnd (numarul se afla o singura data)
		cititor = r._memo("cititor_oprit", lambda: _CititorOprit(r))
		if cititor is None:
			return False
		_amanate[id(conv)] = (conv, what, cititor)
		ceas.start(0, True)
	except Exception as e:
		_amanate.pop(id(conv), None)
		if C is not None:
			C.log_once("evEnd amanat", e)
		return False
	return True


def _renunta_end(conv):
	_amanate.pop(id(conv), None)


def _la_ceas_amanare():
	lista = list(_amanate.values())
	_amanate.clear()
	for conv, what, cititor in lista:
		try:
			conv._trimite_amanat(what, cititor)
		except Exception as e:
			if C is not None:
				C.log_once("evEnd amanat", e)

M_BASE = EV_ALL | EV_INFO
M_VIDEO = M_BASE | EV_VIDEO
M_HBB = M_BASE | EV_HBB
M_EPG = M_BASE | EV_EPG

# nume -> (metoda, e boolean, masca de evenimente)
TYPES = {
	"TechLeft": ("_tech_left", False, M_BASE),
	"TechRight": ("_tech_right", False, M_VIDEO),
	"Satellite": ("_satellite", False, M_BASE),
	# reteaua citita la scanare (Components/HdsRetele.py, numai pe imaginea HDSatelit; altfel gol): numele si ID-ul ei
	# ("Cablu Targu Jiu · NID 53") si numarul canalului dat de operator ("23"); TechLeft,...,Retea pune numele retelei in
	# locul cuvantului "Cablu" la cablu
	"Network": ("_network", False, M_BASE),
	"Lcn": ("_lcn", False, M_BASE),
	"OrbitalPosition": ("_orbital", False, M_BASE),
	"Frequency": ("_frequency", False, M_BASE),
	"Polarization": ("_polarization", False, M_BASE),
	"SymbolRate": ("_symbol_rate", False, M_BASE),
	"Fec": ("_fec", False, M_BASE),
	"Modulation": ("_modulation", False, M_BASE),
	"SrFec": ("_sr_fec", False, M_BASE),
	"System": ("_system", False, M_BASE),
	"MisPls": ("_mis_pls", False, M_BASE),
	"Rolloff": ("_rolloff", False, M_BASE),
	"ReceptionType": ("_reception_type", False, M_BASE),
	"ReceptionName": ("_reception_name", False, M_BASE),
	"Video": ("_video", False, M_VIDEO),
	"VideoCodec": ("_video_codec", False, M_VIDEO),
	"Resolution": ("_resolution", False, M_VIDEO),
	"Format": ("_format", False, M_VIDEO),
	"Audio": ("_audio", False, M_BASE),
	"AudioCodec": ("_audio_codec", False, M_BASE),
	"AudioLanguage": ("_audio_language", False, M_BASE),
	"Tracks": ("_tracks", False, M_BASE),
	"Bitrate": ("_bitrate", False, M_BASE),
	"Ids": ("_ids", False, M_BASE),
	"Pids": ("_pids", False, M_BASE),
	"PcrPmt": ("_pcr_pmt", False, M_BASE),
	"Access": ("_access", False, M_BASE),
	"Caids": ("_caids", False, M_BASE),
	"TxtHbbtv": ("_txt_hbbtv", False, M_HBB),
	"Provider": ("_provider", False, M_BASE),
	# capul InfoBar / SecondInfoBar: in locul ServiceName Reference si al render="ChannelNumber"
	"Reference": ("_reference", False, EV_ALL),
	"ChannelNumber": ("_channel_number", False, EV_ALL),
	# numele serviciului (ca ServiceName); Name,IfNumber = numai cand canalul are numar in lista (numele sta dupa
	# numar), Name,IfNoNumber = numai cand nu are (numele sta in locul numarului, fara loc gol in stanga)
	"Name": ("_name", False, EV_ALL),
	"HasService": ("_has_service", True, M_BASE),
	# o inregistrare merge acum (semnul REC al barei Clasic): se reciteste la pornirea si oprirea inregistrarilor
	"IsRecording": ("_is_recording", True, 0),
	"IsCrypted": ("_is_crypted", True, M_BASE),
	"IsFta": ("_is_fta", True, M_BASE),
	"IsSD": ("_is_sd", True, M_VIDEO),
	"IsHD": ("_is_hd", True, M_VIDEO),
	"IsFHD": ("_is_fhd", True, M_VIDEO),
	"IsUHD": ("_is_uhd", True, M_VIDEO),
	"IsHDAny": ("_is_hd_any", True, M_VIDEO),
	"IsHDR": ("_is_hdr", True, M_VIDEO),
	"Is169": ("_is_169", True, M_VIDEO),
	"Is43": ("_is_43", True, M_VIDEO),
	"Is51": ("_is_51", True, M_BASE),
	"HasTxt": ("_has_txt", True, M_BASE),
	"HasSub": ("_has_sub", True, M_BASE),
	"HasHbbtv": ("_has_hbbtv", True, M_HBB),
	# semnul rosu HbbTV: aplicatie de pornit la ROSU in AIT-ul canalului redat si setarea pornita (numai pe imaginea
	# HDSatelit, HdsCommon.hbbtv_rosu); pe alte imagini mereu fals
	"HbbtvRosu": ("_hbbtv_rosu", True, M_HBB),
	"HasTracks": ("_has_tracks", True, M_BASE),
	"IsRadio": ("_is_radio", True, M_BASE),
	"IsStream": ("_is_stream", True, M_BASE),
	# DVB-I (Components/HdsDvbIDate): canalul are si varianta de internet (sau e canalul DVB-I insusi);
	# canalul merge acum prin internet (buchetul DVB-I sau trecerea singura pe internet) si textul pentru locul
	# semnalului ("prin internet" si starea retelei); pe alte imagini mereu fals / gol
	"HasDvbI": ("_has_dvbi", True, M_BASE),
	"ViaInternet": ("_via_internet", True, M_BASE),
	"DvbIText": ("_dvbi_text", False, M_BASE),
	"ViaInternetText": ("_via_internet_text", False, M_BASE),
	"ViaInternetNet": ("_via_internet_net", False, M_BASE),
	"IsFile": ("_is_file", True, M_BASE),
	"IsDvbS": ("_is_dvbs", True, M_BASE),
	"IsDvbC": ("_is_dvbc", True, M_BASE),
	"IsDvbT": ("_is_dvbt", True, M_BASE),
	"IsT2mi": ("_is_t2mi", True, M_BASE),
	"IsDab": ("_is_dab", True, M_BASE),
	# pagina tehnica extinsa: transponder (satelit, cablu, terestru)
	"Bandwidth": ("_bandwidth", False, M_BASE),
	"Constellation": ("_constellation", False, M_BASE),
	"CodeRate": ("_code_rate", False, M_BASE),
	"GuardInterval": ("_guard_interval", False, M_BASE),
	"TransmissionMode": ("_transmission_mode", False, M_BASE),
	"Hierarchy": ("_hierarchy", False, M_BASE),
	"Plp": ("_plp", False, M_BASE),
	"Inversion": ("_inversion", False, M_BASE),
	"RolloffPilot": ("_rolloff_pilot", False, M_BASE),
	"T2mi": ("_t2mi", False, M_BASE),
	"TerrChannel": ("_terr_channel", False, M_BASE),
	"IsDvbT2": ("_is_dvbt2", True, M_BASE),
	"IsDvbS2": ("_is_dvbs2", True, M_BASE),
	"IsCableAnnexC": ("_is_cable_annex_c", True, M_BASE),
	# pagina tehnica extinsa: serviciu, PID-uri, acces (fara date de la modulul de acces)
	"Sid": ("_sid", False, M_BASE),
	"TsidOnid": ("_tsid_onid", False, M_BASE),
	"Namespace": ("_namespace", False, M_BASE),
	"ServiceType": ("_service_type", False, M_VIDEO),
	"PidPmt": ("_pid_pmt", False, M_BASE),
	"PidPcr": ("_pid_pcr", False, M_BASE),
	"PidVideo": ("_pid_video", False, M_BASE),
	"PidTxt": ("_pid_txt", False, M_BASE),
	"PidAudioAll": ("_pid_audio_all", False, M_BASE),
	"PidSubAll": ("_pid_sub_all", False, M_BASE),
	"CaRow": ("_ca_row", False, M_BASE),
	"CaMore": ("_ca_more", False, M_BASE),
	# pagina tehnica extinsa: piste
	"AudioTrack": ("_audio_track", False, M_BASE),
	"AudioTrackOn": ("_audio_track_on", True, M_BASE),
	"AudioMore": ("_audio_more", False, M_BASE),
	"SubTrack": ("_sub_track", False, M_BASE),
	"SubTrackOn": ("_sub_track_on", True, M_BASE),
	"SubMore": ("_sub_more", False, M_BASE),
	# pagina 3 cu cursor (afisajul interactiv): randul n din fereastra derulata a coloanei, cu numarul de
	# randuri vazute ca al doilea argument (`SelAudio,3,11,P3`); SelRow,a3 / s3 / x3 = cursorul e pe randul acela
	"SelAudio": ("_sel_audio", False, M_BASE),
	"SelAudioOn": ("_sel_audio_on", True, M_BASE),
	"SelSub": ("_sel_sub", False, M_BASE),
	"SelSubOn": ("_sel_sub_on", True, M_BASE),
	"SelRow": ("_sel_row", True, M_BASE),
	"SelExtra": ("_sel_extra", False, M_BASE),
	"SelMore": ("_sel_more", False, M_BASE),
	"HbbtvRow": ("_hbbtv_row", False, M_HBB),
	# pagina 3: iesirea sunetului pentru pista care merge (Components/HdsSunet.stare, numai pe imaginea HDSatelit; pe
	# alte imagini text gol): „Sunet: AC3, trimis neschimbat la televizor”, apoi de ce si, la trimitere, volumul
	"SoundState": ("_sound_state", False, M_BASE),
	"SoundWhy": ("_sound_why", False, M_BASE),
	# pagini (rotire automata, condusa de HdsSignal PageTick): se schimba doar la schimbarea paginii
	"Page": ("_page_on", True, 0),
	"PageDot": ("_page_dot", True, 0),
	"PageDotOn": ("_page_dot_on", True, 0),
	"PageDots": ("_page_dots", False, 0),
	"PageTitle": ("_page_title", False, EV_START),
	# pagina 2: antena si tuner (setarile citite, niciodata scrise; fara unghiuri si coordonate)
	"TunerFull": ("_tuner_full", False, M_BASE),
	"NimConfigMode": ("_nim_config_mode", False, M_BASE),
	"Diseqc": ("_diseqc", False, M_BASE),
	"Lnb": ("_lnb", False, M_BASE),
	"LnbBand": ("_lnb_band", False, M_BASE),
	"RotorMode": ("_rotor_mode", False, M_BASE),
	"HasRotor": ("_has_rotor", True, M_BASE),
	"Antenna5V": ("_antenna_5v", False, M_BASE),
	# pagina 5: ghidul canalului, navigabil. Lista din dreapta: EpgRow,<n>,<randuri vazute> (textul randului n din
	# fereastra derulata), EpgRowOn,<n> (cursorul), EpgRowNow,<n> (emisiunea de acum), EpgRowRec / EpgRowZap,<n>
	# (temporizator de inregistrare / de comutare), EpgMore („1-8 / 42”), EpgHasList. Stanga: emisiunea aleasa
	# (EpgSelWhen, EpgSelTitle, EpgSelTimes cu genul si varsta doar cand exista, EpgSelShort, EpgSelLong). Banda:
	# EpgKey,<culoare> (textul tastei, numai unde tasta lucreaza)
	"EpgRow": ("_epg_row", False, M_EPG),
	"EpgRowOn": ("_epg_row_on", True, M_EPG),
	"EpgRowNow": ("_epg_row_now", True, M_EPG),
	"EpgRowRec": ("_epg_row_rec", True, M_EPG),
	"EpgRowZap": ("_epg_row_zap", True, M_EPG),
	"EpgMore": ("_epg_more", False, M_EPG),
	"EpgHasList": ("_epg_has_list", True, M_EPG),
	"EpgSelWhen": ("_epg_sel_when", False, M_EPG),
	"EpgSelTitle": ("_epg_sel_title", False, M_EPG),
	"EpgSelTimes": ("_epg_sel_times", False, M_EPG),
	"EpgSelShort": ("_epg_sel_short", False, M_EPG),
	"EpgSelLong": ("_epg_sel_long", False, M_EPG),
	"EpgKey": ("_epg_key", False, M_EPG),
	# randurile de ajutor ale ghidului (pagina 5) si ale listei CAID (pagina 4): ce fac acum sagetile si OK
	"EpgHelp": ("_epg_help", False, M_EPG),
	"CaHelp": ("_ca_help", False, M_BASE),
	# pagina 5 de dinainte (raman pentru alte ecrane si skinuri): emisiunea de acum si urmatoarele
	"EventTitle": ("_event_title", False, M_EPG),
	"EventTimes": ("_event_times_text", False, M_EPG),
	"EventShort": ("_event_short", False, M_EPG),
	"EventLong": ("_event_long", False, M_EPG),
	"Genre": ("_genre", False, M_EPG),
	"Rating": ("_rating", False, M_EPG),
	"NextEvent": ("_next_event", False, M_EPG),
	"HasEpg": ("_has_epg", True, M_EPG),
	# pagina 6: receptorul (citit o singura data)
	"BoxName": ("_box_name", False, EV_START),
	"ImageName": ("_image_name", False, EV_START),
	"Chipset": ("_chipset", False, EV_START),
	# numarul nucleelor pe randul lui (Label,cnt_cores,...,IfValue=Cores), cand Chipset are NoCores
	"Cores": ("_cores", False, EV_START),
	# placa are cpufreq (frecventa procesorului): pentru eticheta FRECVENȚĂ cu IfValue=HasCpuFreq
	"HasCpuFreq": ("_has_cpu_freq", True, EV_START),
	"HasTemp": ("_has_temp", True, EV_START),
	# coloana procesorului de pe pagina 6 (Components/HdsProcesor, numai pe imaginea HDSatelit): etichetele se scriu
	# numai cand campul are valoare (IfValue=HasCpuMod ...); HasProcesor = macar unul
	"HasCpuMod": ("_has_cpu_mod", True, EV_START),
	"HasCpuVolt": ("_has_cpu_volt", True, EV_START),
	"HasCpuTrepte": ("_has_cpu_trepte", True, EV_START),
	"HasProcesor": ("_has_procesor", True, EV_START),
	# CAM-ul care decodeaza: numele modulului CI din slot sau "Altele" (fara date de la programe de decodare)
	"CamName": ("_cam_name", False, M_VIDEO),
	"HasCam": ("_has_cam", True, M_VIDEO),
	# timp, cu sursa session.Event_Now (trimite CHANGED_ALL la evenimente)
	"Remaining": ("_remaining", False, EV_ALL),
	"Elapsed": ("_elapsed", False, EV_ALL),
	"Duration": ("_duration", False, EV_ALL),
}

# tipurile cu cronometru (textul se schimba cu minutul)
TIMED = ("_remaining", "_elapsed")

# Flag,<x>: eticheta flag_<x> cand conditia e adevarata, altfel ""
# (pe o imagine veche un Label pus dupa ConditionalShowHide nu merge, deci textul vine gata filtrat)
FLAGS = {
	"txt": "_has_txt", "sub": "_has_sub", "hbbtv": "_has_hbbtv", "51": "_is_51", "169": "_is_169",
	"hdr": "_is_hdr", "sd": "_is_sd", "hd": "_is_hd", "fhd": "_is_fhd", "uhd": "_is_uhd",
	"crypt": "_is_crypted", "fta": "_is_fta", "radio": "_is_radio", "t2mi": "_is_t2mi", "dab": "_is_dab",
	"cam": "_has_cam", "rec": "_is_recording",
}

# tipurile care urmaresc starea CI si imaginea decodata
CAM_FNS = ("_cam_name", "_has_cam")

DVB_KINDS = ("s", "c", "t", "a")
EMPTY = ("", False)


class _Tick(Poll):
	"""Cronometrul unui tip de timp. Nu e legat de sursa; anunta convertorul care l-a creat."""
	CHANGED_POLL = 4

	def __init__(self, owner):
		Poll.__init__(self)
		self._owner = owner

	def changed(self, what):
		o = self._owner
		if o is not None:
			o._on_tick()


# numele codecurilor cu cratima din motivul sunetului, scrise fara loc de rupere
SUNET_NERUPT = ((u"E-AC-3", u"EAC3"), (u"E-AC3", u"EAC3"), (u"AC-3", u"AC3"), (u"HE-AAC", u"HE\u00a0AAC"),
	(u"DTS-HD", u"DTS\u00a0HD"))


def _nerupt(text):
	"""Numele codecurilor fara loc de rupere: eLabel rupe randul si dupa cratima („E-” / „AC3”), iar fonturile skinului
	nu au cratima care nu se rupe (U+2011)."""
	for a, b in SUNET_NERUPT:
		text = text.replace(a, b)
	return text


# ---------------------------------------------------------------- numarul canalului din lista de canale

# flags din eServiceReference: dosarele (buchetele) si marcajele nu primesc numar in lista
REF_DOSAR = 1
REF_MARCAJ = 64
# cel mult atatea intrari citite dintr-un buchet; peste ele numarul nu se mai cauta
MAX_NUMARATE = 5000
# semnele de nume scurt din numele DVB (EN 300 468), ca text Python sau ramase ca octeti UTF-8
SEMNE_NUME_SCURT = (u"\xc2\x86", u"\xc2\x87", u"\x86", u"\x87")


def _flags(text):
	"""flags-urile unei referinte scrise ca text („tip:flags:...”), 0 daca nu se pot citi."""
	try:
		return int(text.split(":", 2)[1])
	except Exception:
		return 0


def _cale(ref):
	try:
		return ref.getPath() or ""
	except Exception:
		return ""


def _retele():
	"""Components/HdsRetele.py (retelele citite la scanare, numerele canalelor date de operator), sau None (alta imagine,
	skinul folosit fara el)."""
	try:
		from Components import HdsRetele
		return HdsRetele
	except ImportError:
		return None


def numar_in_retea(cale, sref):
	"""Numarul operatorului al serviciului `sref` (text) cand lista cu calea `cale` e lista retelei lui (in ordinea
	numerelor operatorului): numarul (> 0), 0 (lista unei retele, dar fara numar pentru serviciu) sau None (alta
	lista)."""
	R = _retele()
	if R is None:
		return None
	cheie = R.retea_din_cale(cale)
	if cheie is None:
		return None
	info = R.pentru_ref(sref)
	if info is not None and info.get("cheie_retea") == cheie and info.get("lcn"):
		return int(info["lcn"])
	return 0


def este_buchet(ref):
	"""Lista are numere numai intr-un buchet (conditia din ChannelSelection.setRoot): calea are FROM BOUQUET, nu e
	lista buchetelor („bouquets.tv” / „bouquets.radio”) si referinta e un dosar. Sateliti, Toate, Furnizori: fara."""
	if ref is None:
		return False
	cale = _cale(ref)
	try:
		dosar = bool(ref.flags & REF_DOSAR)
	except Exception:
		dosar = False
	return dosar and "FROM BOUQUET" in cale and 'FROM BOUQUET "bouquets.' not in cale


def _continut(centru, ref, fel="CS"):
	"""Intrarile listei date de ref, in ordinea listei, citite cu getContent(fel): "C" referintele de comparat, "S"
	referintele ca text (fiecare o lista de siruri), "CS" perechile (referinta de comparat, referinta ca text); [] daca
	nu se poate. Fiecare chemare face o lista noua (o lista din eServiceCenter se citeste o singura data)."""
	lista = centru.list(ref)
	if lista is None:
		return []
	return lista.getContent(fel, False) or []


def _canale(texte):
	"""Cate canale (fara dosare si marcaje) sunt printre referintele ca text."""
	return len([1 for s in texte[:MAX_NUMARATE] if not _flags(s) & (REF_DOSAR | REF_MARCAJ)])


def _deplasare(centru, buchet, fa_ref):
	"""Cu „Mai multe buchete”: cate canale au buchetele dinaintea lui (ca ChannelSelection.getBouquetNumOffset, dar
	pe lista buchetelor TV sau radio, dupa buchet); cu un singur buchet: 0."""
	try:
		from Components.config import config
		if not config.usage.multibouquet.value:
			return 0
	except Exception:
		return 0
	cale = _cale(buchet)
	fel = (2, "radio") if '.radio"' in cale else (1, "tv")
	radacina = fa_ref('1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.%s" ORDER BY bouquet' % fel)
	n = 0
	for s in _continut(centru, radacina, "S"):
		if not _flags(s) & REF_DOSAR:
			continue
		b = fa_ref(s)
		if _cale(b) == cale:
			return n
		n += _canale(_continut(centru, b, "S"))
	return 0


def _numar_in_buchet(centru, buchet, cheie, fa_ref, ref=None):
	"""Deplasarea buchetului + locul canalului `cheie` (referinta de comparat a lui `ref`) printre canalele lui (1, 2,
	...), sau 0.

	Cand lista stie sa numere singura (hdsChannelNumber, in enigma2-ul imaginii), locul vine de acolo, fara niciun sir
	Python: 0 = nu e printre canalele numarate, -1 = lista nu stie numara (atunci citirea de mai jos, pe o lista noua,
	fiindca prima s-a consumat; la fel la o exceptie). Altfel (alte imagini) intai numai referintele de comparat
	(getContent "C": un sir pe intrare, fara tupluri): cand canalul nu e in buchet, cum e la fiecare zap TV buchetul
	tinut minte al listei radio, raspunsul e 0 fara alta citire si fara parcurgere (parcurgerea de mai jos n-ar avea cu
	ce sa se potriveasca). Cand e, textele (getContent "S", aceeasi ordine) dau numaratoarea, ca inainte; daca cele doua
	citiri nu au aceeasi lungime, perechile se citesc din nou dintr-o bucata."""
	lista = centru.list(buchet)
	if lista is None:
		return 0
	numara = getattr(lista, "hdsChannelNumber", None) if ref is not None else None
	if numara is not None:
		try:
			n = numara(ref, MAX_NUMARATE)
		except Exception:
			n = -1
		if n == 0:
			return 0
		if n > 0:
			return _deplasare(centru, buchet, fa_ref) + n
		lista = centru.list(buchet)
		if lista is None:
			return 0
	comparate = lista.getContent("C", False) or []
	if cheie not in comparate:
		return 0
	texte = _continut(centru, buchet, "S")
	intrari = zip(comparate, texte) if len(texte) == len(comparate) else _continut(centru, buchet, "CS")
	n = 0
	for i, (c, s) in enumerate(intrari):
		if i >= MAX_NUMARATE:
			return 0
		if _flags(s) & (REF_DOSAR | REF_MARCAJ):
			continue
		n += 1
		if c == cheie:
			return _deplasare(centru, buchet, fa_ref) + n
	return 0


def _capat(locul, fa_ref):
	"""Lista de la capatul caii tinute minte (config.tv.lastroot / config.radio.lastroot, referinte despartite prin ';')."""
	cale = [x for x in (locul or "").split(";") if x]
	return fa_ref(cale[-1]) if cale else None


def _radacini(fa_ref):
	"""Listele din care poate fi pornit serviciul redat, in ordine: alta lista de canale deschisa acum (lista radio),
	radacina listei TV a barei (sau, cat n-are inca radacina, ca dupa pornirea pe ultimul canal, locul ei tinut minte),
	apoi locul tinut minte al listei radio (cand lista radio e inchisa)."""
	try:
		from Screens.InfoBar import InfoBar
		from Components.config import config
	except ImportError:
		return []
	bara = InfoBar.instance
	if bara is None:
		return []
	lista_tv = getattr(bara, "servicelist", None)
	try:
		alta = bara.session.current_dialog
	except Exception:
		alta = None
	out = []
	r = None
	if alta is not None and alta is not lista_tv and hasattr(alta, "servicePathRadio") and hasattr(alta, "getRoot"):
		r = alta.getRoot()
		out.append(r)
	radio_deschis = r is not None
	r = lista_tv.getRoot() if lista_tv is not None else None
	out.append(r if r is not None else _capat(config.tv.lastroot.value, fa_ref))
	if not radio_deschis:
		out.append(_capat(config.radio.lastroot.value, fa_ref))
	return [x for x in out if x is not None]


def numar_in_lista(sref):
	"""Numarul serviciului `sref` (eServiceReference sau text) in lista de canale din care a pornit, ca in lista:
	deplasarea buchetului + locul printre canale (dosarele si marcajele nu se numara). 0 cand lista nu e un buchet
	(Sateliti, Toate, Furnizori) sau serviciul nu e in ea. Pentru enigma2-ul fara numar in referinta (getChannelNum);
	niciodata o exceptie."""
	try:
		from enigma import eServiceCenter, eServiceReference
	except ImportError:
		return 0
	if not sref:
		return 0
	try:
		radacini = _radacini(eServiceReference)
		if not radacini:
			return 0
		ref = sref
		if not hasattr(ref, "toCompareString"):
			ref = eServiceReference(sref if isinstance(sref, str) else sref.encode("utf-8"))  # Python 2: octeti
		compara = getattr(ref, "toCompareString", None)
		if compara is None:
			return 0
		cheie = compara()
		centru = eServiceCenter.getInstance()
		vazute = set()
		for radacina in radacini:
			cale = _cale(radacina)
			if cale in vazute:
				continue
			# lista unei retele (cablul operatorului): numarul dat de operator, ca in lista
			n = numar_in_retea(cale, ref.toString())
			if n is not None:
				vazute.add(cale)
				if n > 0:
					return n
				continue
			if not este_buchet(radacina):
				continue
			vazute.add(cale)
			n = _numar_in_buchet(centru, radacina, cheie, eServiceReference, ref)
			if n > 0:
				return n
	except Exception as e:
		if C is not None:
			C.log_once("numar_in_lista", e)
	return 0


def numar_canal(source, sref):
	"""Numarul canalului redat: din referinta sursei, pe imaginile care il tin acolo (session.CurrentService.serviceref
	cu getChannelNum, pus de lista la zap), altfel din lista de canale (numar_in_lista). 0 = fara numar. Referinta
	navigatiei nu se foloseste: la evStart e inca cea veche (Navigation.playService o schimba dupa pornire)."""
	ref = getattr(source, "serviceref", None)
	fn = getattr(ref, "getChannelNum", None)
	if fn is not None:
		try:
			return max(int(fn() or 0), 0)
		except Exception:
			return 0
	return numar_in_lista(sref)


def nume_curat(nume):
	"""Numele serviciului fara semnele de nume scurt (ca ServiceName)."""
	t = C.u(nume)
	for s in SEMNE_NUME_SCURT:
		t = t.replace(s, u"")
	return t


def _nume_serviciu(info):
	"""Numele din informatia serviciului redat (iServiceInformation.getName), curatat; gol daca nu se poate citi."""
	try:
		citeste = getattr(info, "getName", None)
		return nume_curat(citeste()) if citeste is not None else u""
	except Exception:
		return u""


def cadre_miimi(v):
	"""sFrameRate adus la miimi de cadru pe secunda (25000 = 25 cadre/s); 0 cand nu se stie.

	Pana la primul eveniment de rata al driverului, decodorul (lib/dvb/decoder.cpp, readMpegProc) citeste
	/proc/stb/vmpeg/0/framerate cu %x, desi fisierul e zecimal: 25000 ajunge 0x25000 = 151552 (pe bara „576i 152”).
	Peste 120 de cadre/s, o valoare a carei scriere hex are numai cifre se citeste inapoi zecimal, daca iese o rata
	plauzibila (20-120 cadre/s); alte valori peste 120 de cadre/s nu se afiseaza. Unele imagini dau cadre intregi
	(25), nu miimi."""
	try:
		v = int(v)
	except (TypeError, ValueError):
		return 0
	if v <= 0:
		return 0
	if v < 1000:
		return v * 1000
	if v > 120000:
		h = "%x" % v
		if h.isdigit() and 20000 <= int(h) <= 120000:
			return int(h)
		return 0
	return v


class HdsInfo(Converter):
	def __init__(self, arg):
		Converter.__init__(self, arg)
		self._fn = None
		self._isbool = False
		self._mask = 0
		self._label = None
		self._upper = False
		self._opts = ()
		self._flag = None
		self._val = None
		self._what = None
		self._gen = -1
		self._tick = None
		self._due = None
		self._primed = set()
		self._page = 0
		self._filters = ()
		self._cam = False
		self._ifvalue = None
		self._fit = None
		self._amana = False
		self._cititor = None
		try:
			self._setup(arg)
		except Exception as e:
			self._fn = None
			self._label = None
			if C is not None:
				C.log_once("init %r" % (arg,), e)
		# numarul din lista de canale: evEnd amanat (vezi _amana_end); numai fara filtre (OnS, ...), care ar citi si
		# altceva din serviciu
		self._amana = not self._filters and (self._fn == "_channel_number" or (self._fn == "_name" and
			("IfNumber" in self._opts or "IfNoNumber" in self._opts)))

	def _setup(self, arg):
		if C is None:
			return
		parts = [p.strip() for p in str(arg or "").split(",")]
		name = parts[0] if parts else ""
		self._opts = tuple(parts[1:])
		C.refresh_lang()
		# P<n>: textul e gol cat pagina n nu se vede; OnS/OnC/OnT/OnDvb/OnIp: doar la felul acela de receptie
		self._page, self._filters = C.parse_page_filters(parts[2:] if name == "Label" else parts[1:])
		# Fit=<font>:<marime>:<latime>: se citeste, dar textul ramane intreg (un rand care nu incape deruleaza,
		# lib/gui/elabel.h)
		if hasattr(C, "parse_fit"):
			self._fit = C.parse_fit(parts[1:])
		if self._page:
			C.page_subscribe(self, self._page)
		if name == "Label":
			self._label = parts[1] if len(parts) > 1 else ""
			self._upper = "Upper" in parts[2:]
			if self._filters:
				self._mask = M_BASE
			# IfValue=<Tip>: eticheta se scrie numai cand tipul numit da text (sau e adevarat) pentru serviciul redat
			for p in parts[2:]:
				if p.startswith("IfValue="):
					spec = TYPES.get(p[8:])
					if spec is not None:
						self._ifvalue = spec[0]
						self._mask |= spec[2]
			return
		if name in ("Page", "PageDot", "PageDotOn", "PageDots", "PageTitle"):
			n = 0
			if name == "Page":
				try:
					n = int(parts[1])
				except Exception:
					n = 0
				n = n if n in C.PAGES else 0
			if n or name != "Page":
				C.page_subscribe(self, n)
		if name == "Flag":
			x = parts[1] if len(parts) > 1 else ""
			cond = FLAGS.get(x)
			if cond is None:
				print("[HdsInfo] Flag necunoscut: %r" % (arg,))
				return
			self._flag = (cond, "flag_" + x)
			self._fn, self._isbool, self._mask = "_flag_text", False, M_VIDEO | EV_HBB
			if cond in CAM_FNS:
				self._cam_on()
			if cond == "_is_recording":
				self._rec_on()
			return
		spec = TYPES.get(name)
		if spec is None:
			print("[HdsInfo] tip necunoscut: %r" % (arg,))
			return
		self._fn, self._isbool, self._mask = spec
		if self._fn in CAM_FNS:
			self._cam_on()
		if self._fn == "_is_recording":
			self._rec_on()
		if self._fn in ("_sel_audio", "_sel_sub") and len(self._opts) > 1:
			C.sel_visible("a" if self._fn == "_sel_audio" else "s", self._opts[1])
		if self._fn == "_epg_row" and len(self._opts) > 1:
			C.epg_visible(self._opts[1])

	def _cam_on(self):
		self._cam = True
		C.cam_subscribe(self)

	def _rec_on(self):
		if hasattr(C, "rec_subscribe"):
			C.rec_subscribe(self)

	def _on_rec(self):
		"""Chemat de HdsCommon cand porneste sau se opreste o inregistrare (Navigation.record_event)."""
		try:
			self._val = None
			self._what = None
			Converter.changed(self, (self.CHANGED_ALL,))
		except Exception as e:
			if C is not None:
				C.log_once("rec", e)

	# ------------------------------------------------------------ legatura cu enigma2

	def changed(self, what):
		try:
			kind = what[0]
			if kind == self.CHANGED_SPECIFIC:
				bits = _EVBITS.get(what[1], 0)
				if not bits:
					return
				if bits & EV_START and C is not None:
					C.refresh_lang()
				if bits & EV_EPG and C is not None:
					C.epg_changed(what)
				if self._cam and C is not None and what[1] in _CAMEV:
					C.cam_event(what, _CAMEV[what[1]])
				if self._page and C is not None and _pagina_ascunsa(self._page):
					# pagina lui nu se vede: nimic spre widget; se reciteste la intrarea in pagina
					self._val = None
					self._what = None
					return
				if self._label is not None and not self._filters and self._ifvalue is None:
					if C is not None and C.lang_gen() != self._gen:
						self._val = None
						Converter.changed(self, what)
					return
				if bits & self._mask:
					self._val = None
					self._what = what
					if self._amana:
						if what[1] == _EV_END and _EV_END is not None and _amana_end(self, what):
							return
						_renunta_end(self)
					Converter.changed(self, what)
					self._rearm()
				return
			if kind == self.CHANGED_POLL:
				return
			self._val = None
			self._what = None
			if self._page and C is not None and _pagina_ascunsa(self._page):
				return
			Converter.changed(self, what)
			self._rearm()
		except Exception as e:
			if C is not None:
				C.log_once("changed", e)

	def _trimite_amanat(self, what, cititor):
		"""evEnd-ul amanat de _amana_end, la ceasul de 0 ms: trimis numai daca de atunci n-a venit alt eveniment, cu
		valorile serviciului de la evEnd (acelasi text ca daca s-ar fi trimis atunci)."""
		if self._what is not what:
			return
		self._val = None
		self._cititor = cititor
		try:
			Converter.changed(self, what)
		finally:
			self._cititor = None
		self._rearm()

	def _on_page(self):
		"""Chemat de HdsCommon.page_set cand pagina acestui convertor intra sau iese de pe ecran."""
		try:
			self._val = None
			self._what = None
			Converter.changed(self, (self.CHANGED_ALL,))
			self._rearm()
		except Exception as e:
			if C is not None:
				C.log_once("page", e)

	def _on_refresh(self, what):
		"""Chemat de HdsCommon.page_refresh dupa o alegere din afisaj: acelasi `what` pentru toata pagina, deci
		serviciul se citeste o singura data."""
		try:
			self._val = None
			self._what = what
			Converter.changed(self, (self.CHANGED_ALL,))
		except Exception as e:
			if C is not None:
				C.log_once("refresh", e)

	def _on_cam(self):
		"""Chemat de HdsCommon cand starea unui slot CI s-a schimbat (ciStateChanged)."""
		try:
			if self._page and C is not None and _pagina_ascunsa(self._page):
				return
			self._val = None
			self._what = None
			Converter.changed(self, (self.CHANGED_ALL,))
		except Exception as e:
			if C is not None:
				C.log_once("cam", e)

	# ------------------------------------------------------------ prima aratare a unui widget

	def connectDownstream(self, downstream):
		Converter.connectDownstream(self, downstream)
		try:
			self._primed.discard(id(downstream))
		except Exception:
			pass

	def checkSuspend(self):
		Converter.checkSuspend(self)
		try:
			self._prime()
		except Exception as e:
			if C is not None:
				C.log_once("prime", e)

	def _prime(self):
		"""Un widget care se arata prima oara primeste o data CHANGED_ALL.

		render="Picon" (pe mai multe imagini) nu face nimic la CHANGED_DEFAULT, singurul
		mesaj de la creare. Un ecran creat dupa zap (SecondInfoBar) ar ramane gol pana la
		zapul urmator. checkSuspend se cheama la fiecare aratare a oricarui widget legat, deci merge
		si cand convertorul e impartit intre InfoBar si SecondInfoBar si ramane treaz.
		"""
		down = self.downstream_elements
		primed = self._primed
		for d in list(down):
			if not getattr(d, "instance", None) or getattr(d, "suspended", True):
				continue
			k = id(d)
			if k in primed:
				continue
			primed.add(k)
			d.changed((self.CHANGED_ALL,))
		if len(primed) > len(down):
			primed.intersection_update([id(d) for d in down])

	# ------------------------------------------------------------ cronometrul tipurilor de timp

	def doSuspend(self, suspended):
		if self._fn not in TIMED:
			return
		try:
			if suspended:
				if self._tick is not None:
					self._tick.poll_enabled = False
			else:
				self._on_tick()
		except Exception as e:
			if C is not None:
				C.log_once("doSuspend", e)

	def _on_tick(self):
		"""La aratare si la fiecare tic: text nou pentru widget, apoi urmatoarea trezire."""
		try:
			self._val = None
			Converter.changed(self, (self.CHANGED_POLL,))
			self._arm()
		except Exception as e:
			if C is not None:
				C.log_once("tick", e)

	def _rearm(self):
		"""Evenimentul s-a schimbat cat se vede: trezirea se muta la noul minut (sau porneste iar)."""
		if self._fn in TIMED and not self.suspended:
			self._arm()

	def _arm(self):
		if self._val is None:
			self._get()
		due = self._due
		t = self._tick
		if due is None:
			if t is not None:
				t.poll_enabled = False
			return
		ms = max(1000, min(61000, int((due - C._now()) * 1000) + 50))
		if t is None:
			t = self._tick = _Tick(self)
		t.poll_interval = ms
		if not t.poll_enabled:
			t.poll_enabled = True

	def _get(self):
		v = self._val
		if v is not None:
			return v
		v = EMPTY
		try:
			if C is None:
				v = EMPTY
			elif self._page and _pagina_ascunsa(self._page):
				self._due = None
				v = EMPTY
			elif self._label is not None:
				self._gen = C.lang_gen()
				r = C.Reader(self.source, self._what) if (self._filters or self._ifvalue) else None
				if self._filters and not C.filter_ok(r, self._filters):
					v = EMPTY
				elif self._ifvalue is not None and not getattr(self, self._ifvalue)(r):
					v = EMPTY
				else:
					t = C.tr(self._label)
					if self._upper:
						t = C.upper(t)
					v = (C.out(C.ltr(t)), bool(t))
			elif self._fn is not None:
				r = self._cititor if self._cititor is not None else C.Reader(self.source, self._what)
				if self._filters and not C.filter_ok(r, self._filters):
					self._due = None
					res = None
				else:
					res = getattr(self, self._fn)(r)
				if self._isbool:
					v = ("", bool(res))
				else:
					t = C.u(res)
					v = (C.out(C.ltr(t)), bool(t))
		except Exception as e:
			v = EMPTY
			if C is not None:
				C.log_once(self._fn or "label", e)
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
		return 0

	text = property(getText)
	boolean = property(getBoolean)
	value = property(getValue)
	range = 100

	def destroy(self):
		try:
			if C is not None:
				C.page_unsubscribe(self)
				C.cam_unsubscribe(self)
				if hasattr(C, "rec_unsubscribe"):
					C.rec_unsubscribe(self)
		except Exception:
			pass
		try:
			t = self._tick
			self._tick = None
			if t is not None:
				t.poll_enabled = False
				t._owner = None
				Poll.destroy(t)
		except Exception:
			pass
		try:
			self._val = None
			self._what = None
			Converter.destroy(self)
		except Exception:
			pass

	# ------------------------------------------------------------ ajutoare

	def _etp(self, r):
		"""(transponder, fel) pentru campurile de receptie; la DAB/T2-MI prin flux, purtatorul."""
		return C.reader_etp(r)

	def _radio(self, r):
		"""Radio: tip de serviciu 2 sau A (ca lista de radio din enigma2), DAB, flux cu adresa doar audio,
		sau fisier / inregistrare fara PID video dar cu PID audio (inregistrarea unui post de radio are 1:0:0)."""
		return bool(r._memo("radio", lambda: self._radio_calc(r)))

	def _radio_calc(self, r):
		ref = r.ref()
		if ref["stype"] in C.RADIO_STYPES or r.is_dab():
			return True
		k = r.kind()
		if k == "ip":
			return C.is_audio_url(ref["path"])
		if k in ("record", "file"):
			if C.is_audio_url(ref["path"]):
				return True
			return r.geti("sVideoPID") <= 0 and r.geti("sAudioPID") > 0 and r.geti("sVideoHeight") <= 0
		return False

	def _height(self, r):
		if self._radio(r):
			return -1
		return r.geti("sVideoHeight")

	def _dab_name(self, r):
		d = r.rj()
		t = C.u(d.get("tip")).upper() if d else u""
		if t == u"DAB":
			return u"DAB"
		codec = r.gets("sTagCodec").upper()
		if codec.startswith(u"DAB ") and not codec.startswith(u"DAB+"):
			return u"DAB"
		return u"DAB+"

	def _t2_name(self, r):
		"""Un program DVB-T2 din satelit (releul local, http://127.0.0.1:<port>/t2/...): „DVB-T2”, ca in lista de
		canale; un program dintr-un flux de distributie de pe 30W (felul abertis din receptie.json: multiplexul terestru
		spaniol, DVB-T, purtat intreg intr-un PID): „DVB-T”; alt flux T2-MI (transponder, alt URL): „T2-MI”."""
		ref = r.ref()
		if ref["url"] and C.is_local_host(ref["host"]) and [p.lower() for p in ref["urlpath"]][:1] == [u"t2"]:
			if self._t2_abertis(r):
				return u"DVB-T"
			return u"DVB-T2"
		return u"T2-MI"

	def _t2_abertis(self, r):
		return C.u(C.rj_dict(r.rj() or {}, "t2").get("fel")) == u"abertis"

	# ------------------------------------------------------------ text

	def _tech_left(self, r):
		k = r.kind()
		if not k:
			return u""
		if k in DVB_KINDS:
			# TechLeft,Short: fara numele satelitului si fara FEC (locul barei de jos)
			linie = C.tp_line(r.tp(), k, "Short" in self._opts)
			if "Retea" in self._opts and k == "c":
				# TechLeft,...,Retea: la cablu numele retelei citite la scanare in locul cuvantului "Cablu"
				retea = self._retea_nume(r)
				cablu = C.tr("rec_cable")
				if retea and linie.startswith(cablu):
					linie = retea + linie[len(cablu):]
			return linie
		if k == "record":
			tp = r.tp()
			return C.join([C.tr("rec_record"), C.carrier_short(tp)])
		if k == "file":
			return C.tr("rec_file")
		if r.is_dab():
			dab = C.rj_dict(r.rj() or {}, "dab")
			ens = C.u(dab.get("ansamblu")) or r.gets("sDABEnsembleLabel")
			carrier = C.carrier_short(r.carrier_tp())
			if not ens and not carrier and k == "dab_relay":
				return C.join([self._dab_name(r), C.tr("local_stream")])
			return C.join([self._dab_name(r), ens, carrier])
		if r.is_t2mi():
			tp = r.carrier_tp()
			t2 = C.rj_dict(r.rj() or {}, "t2")
			plp = C.ival(t2, "plp_id")
			if self._t2_abertis(r):
				pid = C.ival(t2, "t2mi_pid")
				return C.join([self._t2_name(r), C.carrier_short(tp), (u"PID %d" % pid) if pid > 0 else u""])
			return C.join([self._t2_name(r), C.carrier_short(tp), (u"PLP %d" % plp) if plp >= 0 else u""])
		host = r.ref()["host"]
		return C.join([C.tr("rec_ip"), C.tr("local_stream") if C.is_local_host(host) else host])

	def _tech_right(self, r):
		if r.info() is None:
			return u""
		# NoAccess: fara acces; bara il scrie separat (HdsSignal AccessRest / AccessBox), cu sistemul folosit acum in caseta
		access = u"" if "NoAccess" in self._opts else self._access_text(r, True)
		if self._radio(r):
			n, codec, lang = r.audio()
			return C.join([codec, self._bitrate(r), access])
		return C.join([self._resolution(r), self._video_codec(r), access])

	def _satellite(self, r):
		k = r.kind()
		tp, kk = self._etp(r)
		if kk == "s":
			pos = C.ival(tp, "orbital_position")
			if pos >= 0:
				return C.sat_full(pos)
		if kk == "c":
			# la cablu, numele retelei operatorului citit la scanare (Components/HdsRetele.py), cand se stie
			return self._retea_nume(r) or C.tr("rec_cable")
		if kk == "t":
			return C.tr("rec_terr")
		if kk == "a":
			return C.tr("rec_atsc")
		if k == "record":
			return C.tr("rec_record")
		if k == "file":
			return C.tr("rec_file")
		if k in ("ip", "dab_relay", "dab_streamer", "t2mi_url"):
			return C.tr("rec_ip")
		return u""

	def _retea_info(self, r):
		"""Reteaua serviciului redat din scanarile de dinainte ({"retea", "nid", "lcn", ...}), sau None; o data pe citire."""
		if r.info() is None or r.kind() not in DVB_KINDS:
			return None

		def citeste():
			R = _retele()
			return R.pentru_ref(r.sref()) if R is not None else None
		return r._memo("retea_scanata", citeste)

	def _retea_nume(self, r):
		info = self._retea_info(r)
		return C.u(info.get("retea")) if info else u""

	def _network(self, r):
		info = self._retea_info(r)
		if not info:
			return u""
		nume = C.u(info.get("retea"))
		return C.join([nume, u"NID %d" % int(info.get("nid") or 0)]) if nume else u"NID %d" % int(info.get("nid") or 0)

	def _lcn(self, r):
		info = self._retea_info(r)
		return (u"%d" % int(info["lcn"])) if info and info.get("lcn") else u""

	def _orbital(self, r):
		tp, kk = self._etp(r)
		pos = C.ival(tp, "orbital_position")
		return C.orbital(pos) if kk == "s" and pos >= 0 else u""

	def _frequency(self, r):
		tp, kk = self._etp(r)
		return C.freq_long(tp, kk) if kk else u""

	def _polarization(self, r):
		tp, kk = self._etp(r)
		if kk != "s":
			return u""
		key = C.SAT_POL_KEY.get(C.ival(tp, "polarization"))
		return C.tr(key) if key else u""

	def _symbol_rate(self, r):
		tp, kk = self._etp(r)
		return C.symbol_rate(tp) if kk in ("s", "c") else u""

	def _fec(self, r):
		tp, kk = self._etp(r)
		return C.fec_text(tp, kk) if kk in ("s", "c", "t") else u""

	def _modulation(self, r):
		tp, kk = self._etp(r)
		return C.modulation_text(tp, kk)

	def _sr_fec(self, r):
		tp, kk = self._etp(r)
		if kk in ("s", "c"):
			return C.join([C.symbol_rate(tp), C.fec_text(tp, kk)])
		if kk == "t":
			return C.join([C.bandwidth_text(tp), C.fec_text(tp, kk)])
		return u""

	def _system(self, r):
		tp, kk = self._etp(r)
		return C.system_text(tp, kk)

	def _mis_pls(self, r):
		tp, kk = self._etp(r)
		if kk != "s":
			return u""
		return C.mis_pls(tp) or C.tr("no_value")

	def _rolloff(self, r):
		tp, kk = self._etp(r)
		if kk != "s" or C.ival(tp, "system") != 1:
			return u""
		v = C.ROLLOFF.get(C.ival(tp, "rolloff"))
		return C.fmt_dec(v, 2) if v else u""

	def _reception_type(self, r):
		k = r.kind()
		if not k:
			return u""
		if r.is_dab():
			return self._dab_name(r)
		if r.is_t2mi():
			return self._t2_name(r)
		if k == "s":
			return C.sat_system(r.tp())
		if k == "c":
			return u"DVB-C"
		if k == "t":
			return u"DVB-T2" if C.ter_is_t2(r.tp()) else u"DVB-T"
		if k == "a":
			return u"ATSC"
		if k in ("file", "record"):
			return u"FILE"
		return u"IP"

	def _reception_name(self, r):
		k = r.kind()
		if not k:
			return u""
		if r.is_dab():
			return self._dab_name(r)
		if r.is_t2mi():
			return self._t2_name(r)
		names = {"s": "rec_sat", "c": "rec_cable", "t": "rec_terr", "a": "rec_atsc", "file": "rec_file", "record": "rec_record"}
		return C.tr(names.get(k, "rec_ip"))

	def _video_codec(self, r):
		if self._radio(r):
			return u""
		return C.VIDEO_CODEC.get(r.geti("sVideoType"), u"")

	def _scan(self, r, h, fps):
		"""Litera p / i / "" dupa inaltime.

		Unele placi dau progressive=0 si la 720p50 (Viper 4K V20, HiSilicon), deci:
		720 si 2160 mereu p (in DVB nu exista 720i); altfel ce spune placa;
		daca placa nu spune, doar la receptie DVB: 1080 dupa cadre, 576 i.
		"""
		if h >= 2000 or 700 <= h <= 740:
			return u"p"
		prog = r.geti("sProgressive")
		if prog in (0, 1):
			return C.PROGRESSIVE[prog]
		k = r.kind()
		if k not in DVB_KINDS and k not in ("record", "t2mi_url"):
			return u""
		if 1000 <= h <= 1100:
			if fps >= 48000:
				return u"p"
			return u"i" if fps > 0 else u""
		if 570 <= h <= 580:
			return u"i"
		return u""

	def _resolution(self, r):
		if self._radio(r):
			return u""
		w = r.geti("sVideoWidth")
		h = r.geti("sVideoHeight")
		if w <= 0 or h <= 0:
			return u""
		fps = cadre_miimi(r.geti("sFrameRate"))
		scan = self._scan(r, h, fps)
		if "Short" in self._opts:
			text = u"%d%s" % (h, scan)  # Resolution,Short / Video,Short / TechRight,Short: 720p 50, 1080i 50
		else:
			text = u"%dx%d%s" % (w, h, scan)
		if scan == u"i" and 0 < fps < 48000:
			fps *= 2  # placa da cadre; la intretesut se scriu campurile: 1080i 50, 576i 50
		if fps > 0:
			text += u" %d" % ((fps + 500) // 1000)
		return text

	def _video(self, r):
		return C.join([self._video_codec(r), self._resolution(r)])

	def _format(self, r):
		if self._radio(r) or r.geti("sVideoWidth") <= 0:
			return u""
		a = r.geti("sAspect")
		aspect = u"16:9" if a in C.ASPECT_WIDE else (u"4:3" if a in C.ASPECT_43 else u"")
		return C.join([aspect, C.GAMMA.get(r.geti("sGamma"), u"")])

	def _audio(self, r):
		n, codec, lang = r.audio()
		return C.join([codec, lang])

	def _audio_codec(self, r):
		return r.audio()[1]

	def _audio_language(self, r):
		return r.audio()[2]

	def _tracks(self, r):
		"""„Număr piste audio: 3 · Număr subtitrări: 1” (forma „eticheta: numar” nu cere plural in nicio limba)."""
		n = r.audio()[0]
		s = r.subtitles()
		if n <= 0 and s <= 0:
			return u""
		return C.join([u"%s: %d" % (C.tr("cnt_audio"), max(n, 0)), u"%s: %d" % (C.tr("cnt_subs"), max(s, 0))])

	def _bitrate(self, r):
		dab = C.rj_dict(r.rj() or {}, "dab")
		kb = C.ival(dab, "kbit")
		if kb > 0:
			return u"%d kbit/s" % kb
		v = r.geti("sTagBitrate")
		if v > 0:
			return u"%d kbit/s" % (v // 1000 if v >= 1000 else v)
		if v == -2:
			s = r.gets("sTagBitrate")
			return s[:16]
		return u""

	def _ids(self, r):
		if r.info() is None:
			return u""
		vals = [r.geti("sSID"), r.geti("sTSID"), r.geti("sONID")]
		if max(vals) <= 0:
			return u""
		if "Hex" in self._opts:
			return C.join([(u"%04X" % v) if v >= 0 else u"-" for v in vals])
		return C.join([(u"%d" % v) if v >= 0 else u"-" for v in vals])

	def _pids(self, r):
		v = r.geti("sVideoPID")
		a = r.geti("sAudioPID")
		if v <= 0 and a <= 0:
			return u""
		f = lambda x: (u"%d" % x) if x > 0 else u"-"
		return u"%s / %s" % (f(v), f(a))

	def _pcr_pmt(self, r):
		pcr = r.geti("sPCRPID")
		pmt = r.geti("sPMTPID")
		return C.join([(u"PCR %d" % pcr) if pcr > 0 else u"", (u"PMT %d" % pmt) if pmt > 0 else u""])

	def _access_text(self, r, short):
		k = r.kind()
		if k not in DVB_KINDS and k != "record":
			return u""
		if short:
			# capul paginii accesului: sistemul decriptat acum primul, „+N” pentru celelalte
			if getattr(self, "_page", 0) == 4 and hasattr(C, "access_head"):
				return C.access_head(r)
			return C.access_short(r)
		caids = r.caids()
		if caids:
			groups = C.group_caids(caids)
			parts = []
			for name, cs in groups[:3]:
				if name.startswith(u"0x"):
					parts.append(name)
				else:
					parts.append(u"%s (%s)" % (name, u", ".join([u"%04X" % c for c in cs[:3]])))
			return C.join(parts)
		# trei stari; nimic cat nu se stie (inainte: FTA pana venea PMT-ul)
		acces = r.acces()
		if acces == "criptat":
			return C.tr("encrypted")
		if acces == "fta":
			return C.tr("fta_short") if short else C.tr("fta")
		return u""

	def _access(self, r):
		return self._access_text(r, "Short" in self._opts)

	def _caids(self, r):
		return u" ".join([u"%04X" % c for c in r.caids()])

	def _txt_hbbtv(self, r):
		if r.info() is None:
			return u""
		t = r.geti("sTXTPID")
		# HbbTV: pe imaginea HDSatelit din baza pistelor (HdsCommon.hbbtv_semnalat), „nu se stie” cand baza nu stie
		return C.join([(u"PID %d" % t) if t > 0 else C.tr("no_value"), C.text_hbbtv(r)])

	def _provider(self, r):
		return r.gets("sProvider")

	def _reference(self, r):
		"""Referinta serviciului redat, pentru render="Picon" (ca ServiceName Reference, fara .meta)."""
		return r.sref() if r.info() is not None else u""

	def _numar_lista(self, r):
		"""Numarul canalului redat in lista de canale (0 = fara numar), citit o data pe eveniment pentru toate
		widgeturile legate de aceeasi sursa (numarul, cele doua nume)."""
		return r._memo("numar_lista", lambda: numar_canal(self.source, r.sref())) or 0

	def _channel_number(self, r):
		"""Numarul din lista de canale (ca render="ChannelNumber"); gol sau `---` (optiunea Dashes)."""
		if r.info() is None:
			return u""
		n = self._numar_lista(r)
		if n > 0:
			return u"%d" % n
		return u"---" if "Dashes" in self._opts else u""

	def _name(self, r):
		"""Numele serviciului redat (ca ServiceName). IfNumber: numai cand canalul are numar in lista; IfNoNumber: numai
		cand nu are. Doua widgeturi cu aceste optiuni muta numele in locul numarului cand numarul lipseste."""
		i = r.info()
		if i is None:
			return u""
		opts = self._opts
		if "IfNumber" in opts or "IfNoNumber" in opts:
			if (self._numar_lista(r) > 0) != ("IfNumber" in opts):
				return u""
		return r._memo("nume_serviciu", lambda: _nume_serviciu(i)) or u""

	# ------------------------------------------------------------ pagina tehnica extinsa: transponder

	def _row_index(self, limita=None):
		"""Numarul randului din argument (`AudioTrack,2` -> 1), sau -1 daca lipseste / e in afara 1..6 (tipurile vechi,
		ca pana acum) sau 1..32 (randurile paginii 3 cu cursor, `limita=C.ROW_LIMIT`)."""
		try:
			n = int(self._opts[0])
		except Exception:
			return -1
		return n - 1 if 1 <= n <= (limita or C.MAX_ROWS) else -1

	def _ter_tp(self, r):
		tp, kk = self._etp(r)
		return tp if kk == "t" else None

	def _bandwidth(self, r):
		tp = self._ter_tp(r)
		return C.bandwidth_text(tp) if tp is not None else u""

	def _constellation(self, r):
		tp = self._ter_tp(r)
		return C.enum_auto(tp, "constellation", C.TER_CONST, 3) if tp is not None else u""

	def _code_rate(self, r):
		tp = self._ter_tp(r)
		return C.code_rate_text(tp) if tp is not None else u""

	def _guard_interval(self, r):
		tp = self._ter_tp(r)
		return C.enum_auto(tp, "guard_interval", C.TER_GUARD, 4) if tp is not None else u""

	def _transmission_mode(self, r):
		tp = self._ter_tp(r)
		return C.enum_auto(tp, "transmission_mode", C.TER_TMODE, 2) if tp is not None else u""

	def _hierarchy(self, r):
		"""Doar DVB-T (in DVB-T2 nu exista)."""
		tp = self._ter_tp(r)
		if tp is None or C.ter_is_t2(tp):
			return u""
		v = C.ival(tp, "hierarchy_information")
		if v == 0:
			return C.tr("none")
		return C.enum_auto(tp, "hierarchy_information", C.TER_HIER, 4)

	def _plp(self, r):
		tp = self._ter_tp(r)
		if tp is None or not C.ter_is_t2(tp):
			return u""
		plp = C.ival(tp, "plp_id")
		return (u"PLP %d" % plp) if plp >= 0 else u""

	def _inversion(self, r):
		tp, kk = self._etp(r)
		return C.on_off(tp, "inversion") if kk in ("s", "c", "t") else u""

	def _rolloff_pilot(self, r):
		tp, kk = self._etp(r)
		if kk != "s" or C.ival(tp, "system") != 1:
			return u""
		v = C.ROLLOFF.get(C.ival(tp, "rolloff"))
		return C.join([C.fmt_dec(v, 2) if v else u"", C.on_off(tp, "pilot")])

	def _t2mi(self, r):
		tp, kk = self._etp(r)
		if kk != "s":
			return u""
		plp = C.ival(tp, "t2mi_plp_id")
		if plp < 0:
			return C.tr("no_value")
		pid = C.ival(tp, "t2mi_pid")
		return C.join([u"PLP %d" % plp, (u"PID %d" % pid) if pid > 0 else u""])

	def _terr_channel(self, r):
		tp = self._ter_tp(r)
		return C.terr_channel_text(tp) if tp is not None else u""

	def _is_dvbt2(self, r):
		tp = self._ter_tp(r)
		return tp is not None and C.ter_is_t2(tp)

	def _is_dvbs2(self, r):
		tp, kk = self._etp(r)
		return kk == "s" and C.ival(tp, "system") == 1

	def _is_cable_annex_c(self, r):
		tp, kk = self._etp(r)
		return kk == "c" and C.ival(tp, "system") == 1

	# ------------------------------------------------------------ pagina tehnica extinsa: serviciu

	def _dvb_service(self, r):
		return r.info() is not None and r.kind() in DVB_KINDS

	def _sid(self, r):
		if not self._dvb_service(r):
			return u""
		sid = r.geti("sSID")
		return (u"%d (%04X)" % (sid, sid)) if sid > 0 else u""

	def _tsid_onid(self, r):
		if not self._dvb_service(r):
			return u""
		return C.id_dec_hex([r.geti("sTSID"), r.geti("sONID")], 4)

	def _namespace(self, r):
		if not self._dvb_service(r):
			return u""
		return C.namespace_text(r.ref()["fields"], r.geti("sNamespace"))

	def _service_type(self, r):
		"""Tipul declarat in lista de canale (SDT); cand imaginea masurata il contrazice (canal HD declarat SD, H.264
		declarat MPEG-2) se scrie limpede ca e cel declarat."""
		if not self._dvb_service(r):
			return u""
		stype = r.ref()["stype"]
		text = C.service_type_text(stype)
		if not text or self._radio(r):
			return text
		h = r.geti("sVideoHeight")
		codec = r.geti("sVideoType")
		sd_declared = stype in (0x01, 0x16)
		mpeg2_declared = stype in (0x01, 0x11)
		if (sd_declared and h >= 720) or (mpeg2_declared and codec in (1, 7)):
			return u"%s (%s)" % (text, C.tr("declared"))
		return text

	def _pid_one(self, r, name):
		if r.info() is None or r.kind() not in DVB_KINDS + ("record",):
			return u""
		v = r.geti(name)
		return (u"%d" % v) if 0 < v < 0x1FFF else u""

	def _pid_pmt(self, r):
		return self._pid_one(r, "sPMTPID")

	def _pid_pcr(self, r):
		return self._pid_one(r, "sPCRPID")

	def _pid_video(self, r):
		return self._pid_one(r, "sVideoPID")

	def _pid_txt(self, r):
		if r.info() is None or r.kind() not in DVB_KINDS + ("record",):
			return u""
		return self._pid_one(r, "sTXTPID") or C.tr("no_value")

	def _pid_audio_all(self, r):
		if r.kind() not in DVB_KINDS + ("record",):
			return u""
		rows, cur = r.track_list()
		pids = []
		for codec, lang, pid in rows:
			if pid > 0 and pid not in pids:
				pids.append(pid)
		if not pids:
			a = r.geti("sAudioPID")
			if a > 0:
				pids.append(a)
		return u" ".join([u"%d" % p for p in pids[:8]])

	def _pid_sub_all(self, r):
		if r.kind() not in DVB_KINDS + ("record",) or r.info() is None:
			return u""
		rows, cur = r.sub_list()
		pids = []
		for e in rows:
			if C.ival({"k": e[0]}, "k") == 0:
				p = C.ival({"p": e[1]}, "p")
				if 0 < p < 0x1FFF and p not in pids:
					pids.append(p)
		if not pids:
			return C.tr("no_value")
		return u" ".join([u"%d" % p for p in pids[:8]])

	def _ca_list(self, r):
		if r.kind() not in DVB_KINDS + ("record",):
			return []
		return C.ca_rows(r.caidpids(), r.caids())

	def _ca_row(self, r):
		i = self._row_index()
		rows = self._ca_list(r)
		return rows[i] if 0 <= i < len(rows) else u""

	def _ca_more(self, r):
		return C.more_text(len(self._ca_list(r)))

	# ------------------------------------------------------------ pagina tehnica extinsa: piste

	def _audio_track(self, r):
		i = self._row_index()
		rows, cur = r.track_list()
		if not 0 <= i < len(rows):
			return u""
		codec, lang, pid = rows[i]
		return C.join([codec, lang, (u"PID %d" % pid) if pid > 0 else u""])

	def _audio_track_on(self, r):
		i = self._row_index()
		rows, cur = r.track_list()
		return 0 <= i < len(rows) and i == cur

	def _audio_more(self, r):
		return C.more_text(len(r.track_list()[0]))

	def _sub_track(self, r):
		i = self._row_index()
		rows, cur = r.sub_list()
		return C.sub_text(rows[i]) if 0 <= i < len(rows) else u""

	def _sub_track_on(self, r):
		i = self._row_index()
		rows, cur = r.sub_list()
		return 0 <= i < len(rows) and C.same_sub(rows[i], cur)

	def _sub_more(self, r):
		return C.more_text(len(r.sub_list()[0]))

	# ------------------------------------------------------------ pagina 3 cu cursor (afisajul interactiv)

	def _sel_audio(self, r):
		i = self._row_index(C.ROW_LIMIT)
		rows, cur = r.track_list()
		if not rows:
			return C.tr("sel_no_audio") if i == 0 and r.info() is not None else u""
		k = C.sel_top(r, "a") + i if i >= 0 else -1
		if not 0 <= k < len(rows):
			return u""
		codec, lang, pid = rows[k]
		# pista aleasa de mana si tinuta minte pe canal (HdsPisteLimbi): scris langa ea, ca omul sa stie de ce nu se schimba
		memo = C.tr("sel_memo") if C.piste_memorat(r)["a"] == k else u""
		return C.join([codec, lang, (u"PID %d" % pid) if pid > 0 else u"", memo])

	def _sel_audio_on(self, r):
		i = self._row_index(C.ROW_LIMIT)
		rows, cur = r.track_list()
		return i >= 0 and cur >= 0 and C.sel_top(r, "a") + i == cur

	def _sel_sub(self, r):
		i = self._row_index(C.ROW_LIMIT)
		if i < 0 or r.info() is None:
			return u""
		k = C.sel_top(r, "s") + i
		rows = r.sub_list()[0]
		m = C.piste_memorat(r)
		if k == 0:
			return C.join([C.tr("sel_no_subs"), C.tr("sel_memo") if m["s"] and m["s_t"] is None else u""])
		if not 0 < k <= len(rows):
			return u""
		memo = C.tr("sel_memo") if m["s"] and m["s_t"] is not None and C.same_sub(rows[k - 1], m["s_t"]) else u""
		return C.join([C.sub_text(rows[k - 1]), memo])

	def _sel_sub_on(self, r):
		i = self._row_index(C.ROW_LIMIT)
		if i < 0 or r.info() is None:
			return False
		k = C.sel_top(r, "s") + i
		rows, cur = r.sub_list()
		if k == 0:
			return cur is None
		return 0 < k <= len(rows) and C.same_sub(rows[k - 1], cur)

	def _sel_row(self, r):
		try:
			col, n = self._opts[0][:1], int(self._opts[0][1:])
		except Exception:
			return False
		return col in ("a", "s", "x") and n >= 1 and r.info() is not None and C.sel_on_row(r, col, n)

	def _sel_extra(self, r):
		i = self._row_index(C.ROW_LIMIT)
		ex = C.sel_extras(r)
		return C.extra_text(r, ex[i]) if 0 <= i < len(ex) else u""

	def _sel_more(self, r):
		col = self._opts[0] if self._opts else ""
		return C.sel_more(r, col) if col in ("a", "s") else u""

	def _sound_state(self, r):
		s = C.sunet_stare(r)
		return _nerupt((s.get("text") or u"") if s else u"")

	def _sound_why(self, r):
		s = C.sunet_stare(r)
		if not s:
			return u""
		return _nerupt(C.join([s.get("motiv") or u"", s.get("volum") or u""], u" "))

	def _hbbtv_row(self, r):
		if r.info() is None:
			return u""
		return u"%s: %s" % (C.tr("sel_hbbtv"), C.text_hbbtv(r))

	def _is_recording(self, r):
		return C.inregistrari_in_curs() > 0

	def _flag_text(self, r):
		cond, key = self._flag
		if not getattr(self, cond)(r):
			return u""
		if key == "flag_radio" and r.is_dab():
			# un post DAB / DAB+: eticheta felului in locul lui RADIO, langa nume (ca in lista de canale)
			return self._dab_name(r)
		return C.tr(key)

	# ------------------------------------------------------------ pagini

	def _page_on(self, r):
		try:
			n = int(self._opts[0])
		except Exception:
			return False
		return n in C.PAGES and C.page_active() == n

	def _page_dot(self, r):
		"""Punctul k (1..6) exista: sunt cel putin k pagini valide (si mai mult de una)."""
		i = self._row_index()
		pos, count = C.page_position()
		return count > 1 and 0 <= i < count

	def _page_dot_on(self, r):
		i = self._row_index()
		pos, count = C.page_position()
		return count > 1 and i == pos - 1

	def _page_dots(self, r):
		return C.page_dots() if len(C.page_valid()) > 1 else u""

	def _page_title(self, r):
		"""« 2 / 6 » · Antenă și tuner (`PageTitle,Upper` cu majuscule)."""
		pos, count = C.page_position()
		t = C.tr(C.PAGE_KEYS.get(C.page_active(), "page_reception"))
		if "Upper" in self._opts:
			t = C.upper(t)
		if count > 1:
			return u"«   %d / %d   »   ·   %s" % (pos, count, t)
		return t


	# ------------------------------------------------------------ pagina 2: antena si tuner

	def _tuner_n(self, r, kinds):
		k = r.kind()
		if k not in kinds:
			# post DAB+ / program DVB-T2 prin releu: tunerul care tine purtatorul (din receptie.json)
			if k in C.FEL_FLUX_PURTATOR:
				ek = C.reader_etp(r)[1]
				if ek in kinds:
					return C.fe_number(r), ek
			return -1, k
		return C.fe_number(r), k

	def _sat_tuner(self, r):
		n, k = self._tuner_n(r, ("s",))
		if n < 0:
			return -1, -1
		return n, C.ival(C.reader_etp(r)[0], "orbital_position")

	def _tuner_full(self, r):
		n, k = self._tuner_n(r, DVB_KINDS)
		return C.tuner_full(n, k) if n >= 0 else u""

	def _nim_config_mode(self, r):
		n, k = self._tuner_n(r, ("s", "c", "t"))
		return C.config_mode_text(n, k) if n >= 0 else u""

	def _diseqc(self, r):
		n, pos = self._sat_tuner(r)
		return C.diseqc_text(n, pos) if n >= 0 else u""

	def _lnb(self, r):
		n, pos = self._sat_tuner(r)
		return C.lnb_text(n, pos) if n >= 0 else u""

	def _lnb_band(self, r):
		n, pos = self._sat_tuner(r)
		return C.lnb_band_text(n, r.tp()) if n >= 0 else u""

	def _rotor_mode(self, r):
		n, pos = self._sat_tuner(r)
		return C.rotor_mode_text(n, pos) if n >= 0 else u""

	def _has_rotor(self, r):
		n, pos = self._sat_tuner(r)
		return n >= 0 and C.has_rotor(n, pos)

	def _antenna_5v(self, r):
		n, k = self._tuner_n(r, ("t",))
		return C.antenna_5v_text(n) if n >= 0 else u""

	# ------------------------------------------------------------ pagina 5: emisiunea

	def _tr(self, fel, text):
		"""traducerea automata a ghidului (HdsCommon.epg_tr), unde exista"""
		fn = getattr(C, "epg_tr", None)
		return fn(fel, text) if fn is not None and text else text

	def _event_title(self, r):
		ev = C.event_data(r, 0)
		return self._tr("titlu", ev["name"]) if ev else u""

	def _event_times_text(self, r):
		return C.event_times_text(C.event_data(r, 0))

	def _event_short(self, r):
		ev = C.event_data(r, 0)
		if not ev or ev["short"] == ev["name"]:
			return u""
		return self._tr("scurta", ev["short"])

	def _event_long(self, r):
		ev = C.event_data(r, 0)
		if not ev or ev["ext"] == ev["short"]:
			return u""
		return self._tr("lunga", ev["ext"])

	def _genre(self, r):
		ev = C.event_data(r, 0)
		return C.genre_text(ev["genre"]) if ev else u""

	def _rating(self, r):
		ev = C.event_data(r, 0)
		return C.rating_text(ev["rating"]) if ev else u""

	def _next_event(self, r):
		"""`NextEvent,<i>`: 21:45  Tagesschau (i = 1..6)."""
		i = self._row_index()
		if i < 0 or r.info() is None:
			return u""
		rows = C.next_events(r)
		if i >= len(rows):
			return u""
		begin, title = rows[i]
		return u"%s  %s" % (C.hhmm(begin), self._tr("titlu", title))

	def _has_epg(self, r):
		return bool(C.event_data(r, 0))

	# ------------------------------------------------------------ pagina 5: ghidul canalului, navigabil

	def _epg_n(self):
		i = self._row_index(C.ROW_LIMIT)
		return i + 1 if i >= 0 else 0

	def _epg_row(self, r):
		n = self._epg_n()
		return C.epg_row_text(r, n) if n else u""

	def _epg_row_on(self, r):
		n = self._epg_n()
		return bool(n) and C.epg_on_row(r, n)

	def _epg_row_now(self, r):
		n = self._epg_n()
		return bool(n) and C.epg_row_now(r, n)

	def _epg_row_rec(self, r):
		n = self._epg_n()
		return bool(n) and C.epg_row_timer(r, n) == u"inregistrare"

	def _epg_row_zap(self, r):
		n = self._epg_n()
		return bool(n) and C.epg_row_timer(r, n) == u"comutare"

	def _epg_more(self, r):
		return C.epg_more_text(r)

	def _epg_has_list(self, r):
		return bool(C.epg_list(r))

	def _epg_sel_when(self, r):
		t = C.epg_when_text(r)
		return C.upper(t) if "Upper" in self._opts else t

	def _epg_sel_title(self, r):
		ev = C.epg_event(r)
		return self._tr("titlu", ev["name"]) if ev else u""

	def _epg_sel_times(self, r):
		return C.event_line(C.epg_event(r))

	def _epg_sel_short(self, r):
		ev = C.epg_event(r)
		if not ev or ev["short"] == ev["name"]:
			return u""
		return self._tr("scurta", C.epg_short_line(ev) if hasattr(C, "epg_short_line") else ev["short"])

	def _epg_sel_long(self, r):
		ev = C.epg_event(r)
		if not ev or ev["ext"] in (ev["short"], ev["name"]):
			return u""
		return self._tr("lunga", ev["ext"])

	def _epg_help(self, r):
		return C.epg_help_text(r) if hasattr(C, "epg_help_text") else u""

	def _ca_help(self, r):
		return C.ca_help_text(r) if hasattr(C, "ca_help_text") else u""

	def _epg_key(self, r):
		return C.epg_key_text(r, self._opts[0] if self._opts else "")

	# ------------------------------------------------------------ pagina 6: receptorul

	def _box_name(self, r):
		return C.box_name()

	def _image_name(self, r):
		# ImageName,Short: fara data din paranteza (randul de jos al meniului Pro: "HD Satelit 0.4.24" incape intreg)
		return C.image_name(scurt="Short" in self._opts)

	def _chipset(self, r):
		return C.chipset_text("NoCores" not in self._opts)

	def _cores(self, r):
		return C.cores_text() if hasattr(C, "cores_text") else u""

	def _has_temp(self, r):
		"""Adevarat cand se poate citi temperatura (HdsProcesor sau un senzor): eticheta TEMPERATURĂ numai atunci."""
		return C.procesor_temperatura() is not None or C.temperature() is not None

	def _has_cpu_freq(self, r):
		return C.cpu_freq() is not None

	def _has_cpu_mod(self, r):
		return bool(C.procesor_camp("setata"))

	def _has_cpu_volt(self, r):
		return bool(C.procesor_camp("tensiune"))

	def _has_cpu_trepte(self, r):
		return bool(C.procesor_camp("trepte"))

	def _has_procesor(self, r):
		return any(C.procesor_camp(k) for k in ("setata", "tensiune", "trepte"))

	# ------------------------------------------------------------ CAM-ul care decodeaza

	def _cam_name(self, r):
		"""Numele modulului CI (cum il da modulul), "Altele" cand imaginea se decodeaza fara modul CI, altfel gol."""
		return C.cam_name(r)

	def _has_cam(self, r):
		"""Adevarat cand CamName nu e gol (modul CI sau "Altele")."""
		return C.cam_source(r)[0] != ""

	# ------------------------------------------------------------ timp (sursa cu .event)

	def _event_times(self):
		"""(inceput, sfarsit, durata) in secunde, sau None. _due se sterge aici."""
		self._due = None
		ev = getattr(self.source, "event", None)
		if not ev:
			return None
		begin = int(ev.getBeginTime() or 0)
		dur = int(ev.getDuration() or 0)
		if begin <= 0 or dur <= 0:
			return None
		C.refresh_lang()
		return begin, begin + dur, dur

	def _minutes(self, n, sign=u""):
		return u"%s%d %s" % (sign, n, C.tr("unit_min"))

	def _remaining(self, r):
		t = self._event_times()
		if t is None:
			return u""
		begin, end, dur = t
		now = int(C._now())
		if now < begin:
			self._due = begin
			return self._minutes(dur // 60)
		if now > end:
			return self._minutes(0, u"+")
		rem = end - now
		self._due = now + rem % 60 + 1
		return self._minutes(rem // 60, u"+")

	def _elapsed(self, r):
		t = self._event_times()
		if t is None:
			return u""
		begin, end, dur = t
		now = int(C._now())
		if now < begin:
			self._due = begin
			return u""
		if now > end:
			return u""
		el = now - begin
		self._due = begin + (el // 60 + 1) * 60
		return self._minutes(el // 60, u"-")

	def _duration(self, r):
		t = self._event_times()
		return self._minutes(t[2] // 60) if t is not None else u""

	# ------------------------------------------------------------ boolean

	def _has_service(self, r):
		return r.info() is not None

	def _is_crypted(self, r):
		k = r.kind()
		return (k in DVB_KINDS or k == "record") and r.acces() == "criptat"

	def _is_fta(self, r):
		# „fta” numai cand s-a aflat (acum sau tinut minte pe canal), nu cat sIsCrypted e inca -1
		return r.kind() in DVB_KINDS and r.acces() == "fta"

	def _is_sd(self, r):
		return 0 < self._height(r) < 720

	def _is_hd(self, r):
		return 720 <= self._height(r) < 1000

	def _is_fhd(self, r):
		return 1000 <= self._height(r) < 1500

	def _is_uhd(self, r):
		return self._height(r) >= 1500

	def _is_hd_any(self, r):
		return self._height(r) >= 720

	def _is_hdr(self, r):
		return not self._radio(r) and r.geti("sGamma") in (1, 2, 3)

	def _is_169(self, r):
		return not self._radio(r) and r.geti("sAspect") in C.ASPECT_WIDE

	def _is_43(self, r):
		return not self._radio(r) and r.geti("sAspect") in C.ASPECT_43

	def _is_51(self, r):
		return r.audio()[1] in C.MULTICHANNEL

	def _has_txt(self, r):
		return r.geti("sTXTPID") > 0

	def _has_sub(self, r):
		return r.subtitles() > 0

	def _has_hbbtv(self, r):
		return C.hbbtv_semnalat(r) is True

	def _hbbtv_rosu(self, r):
		return C.hbbtv_rosu(r)

	def _has_tracks(self, r):
		return r.audio()[0] > 1

	def _is_radio(self, r):
		return r.info() is not None and self._radio(r)

	def _is_stream(self, r):
		return r.info() is not None and r.ref()["url"] and r.kind() != "dab_native"

	def _date_dvbi(self):
		try:
			from Components import HdsDvbIDate
			return HdsDvbIDate
		except ImportError:
			return None

	def _ref_dvbi(self, r):
		"""referinta programului: din info sau, cand fluxul n-a pornit (un canal oprit pe tara), cea pornita de navigare"""
		s = r.sref()
		if s:
			return s
		try:
			import NavigationInstance
			ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
			return ref.toString() if ref is not None else u""
		except Exception:
			return u""

	def _has_dvbi(self, r):
		D = self._date_dvbi()
		if D is None:
			return False
		return bool(self._memo_dvbi(r, "are", lambda: D.areDvbI(self._ref_dvbi(r))))

	def _via_internet(self, r):
		D = self._date_dvbi()
		if D is None:
			return False
		return bool(self._memo_dvbi(r, "prin", lambda: D.esteDvbI(self._ref_dvbi(r))))

	def _memo_dvbi(self, r, nume, fn):
		memo = getattr(r, "_memo", None)
		if memo is None:
			return fn()
		return memo("dvbi:" + nume, fn)

	def _dvbi_text(self, r):
		return u"DVB-I" if self._has_dvbi(r) else u""

	def _via_internet_text(self, r):
		D = self._date_dvbi()
		return _(D.T_PRIN_INTERNET).upper() if D is not None and self._via_internet(r) else u""

	def _via_internet_net(self, r):
		"""starea retelei in locul semnalului ("Internet prin cablu: merge"), cat canalul merge prin internet"""
		if not self._via_internet(r):
			return u""
		try:
			from Components import HdsStareRetea
			return HdsStareRetea.text_ajutor(HdsStareRetea.stare())
		except Exception:
			return u""

	def _is_file(self, r):
		return r.kind() in ("file", "record")

	def _is_dvbs(self, r):
		return self._etp(r)[1] == "s" and r.kind() in ("s", "record")

	def _is_dvbc(self, r):
		return self._etp(r)[1] == "c" and r.kind() in ("c", "record")

	def _is_dvbt(self, r):
		return self._etp(r)[1] == "t" and r.kind() in ("t", "record")

	def _is_t2mi(self, r):
		return r.is_t2mi()

	def _is_dab(self, r):
		return r.is_dab()
