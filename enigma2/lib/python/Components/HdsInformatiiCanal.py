# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsInformatiiCanal: randurile ecranului Informatii despre canal (Screens/ServiceInfo.py, Meniu > Informatii despre
# sistem > Channel Information, cele patru pagini de pe tastele colorate: Rosu Serviciu, Verde PID-uri, Galben
# Multiplex, Albastru Stare tuner), facute o singura data pentru ecran si pentru pagina web /informatii-canal
# (HdsWebControl/canal_info_web.py). Aceleasi surse (iServiceInformation al canalului de acum, frontendInfo, datele
# transponderului din lista de canale) si aceeasi formatare (hex si zecimal, MHz, kS/s, procente).
#
# Un rand e (eticheta, valoare, fel[, cifre]): fel TEXT, HEX, DEC, HEX_DEC, ca in ecran; randuriText() le scrie ca
# ServiceInfoListEntry (eticheta cu doua puncte, valoarea formatata) si sare randurile fara valoare (None).
# Ce ramane in ecran, pentru ca probele vechi il pazesc acolo: getReceiverConnectionInfo (legatura emulatorului cu
# receptorul) si randul "Direct pe receptorul %s"; amandoua intra aici ca argumente.
#
# Fisierul nu importa nimic din enigma2 la incarcare: iServiceInformation, centrul de servicii, nimmanager si
# convertorul transponderului se dau ca argumente.

TYPE_TEXT = 0
TYPE_VALUE_HEX = 1
TYPE_VALUE_DEC = 2
TYPE_VALUE_HEX_DEC = 3


def to_unsigned(x):
	return x & 0xFFFFFFFF


def formateaza(b, valueType=TYPE_TEXT, param=4):
	"""Valoarea unui rand, ca ServiceInfoListEntry: textul ramane, numerele dupa fel."""
	if not isinstance(b, str):
		if valueType == TYPE_VALUE_HEX:
			b = ("0x%0" + str(param) + "x") % to_unsigned(b)
		elif valueType == TYPE_VALUE_DEC:
			b = str(b)
		elif valueType == TYPE_VALUE_HEX_DEC:
			b = ("0x%0" + str(param) + "x (%dd)") % (to_unsigned(b), b)
		else:
			b = str(b)
	return b


def randuriText(Labels):
	"""[(eticheta cu doua puncte sau "", valoarea text)], ca ServiceInfo.fillList."""
	rez = []
	for item in Labels:
		if item[1] is None:
			continue
		prefix = (item[0] + ":") if item[0] else ""
		rez.append((prefix, formateaza(item[1], item[2], item[3] if len(item) > 3 else 4)))
	return rez


def valoare(info, what):
	"""ServiceInfo.getServiceInfoValue: -2 = text, -1 = N/A; fara info, ""."""
	if info is None:
		return ""
	v = info.getInfo(what)
	if v == -2:
		v = info.getInfoString(what)
	elif v == -1:
		v = _("N/A")
	return v


def textHdr(info, I):
	"""Gama imaginii din flux (evenimentul 17 al decodorului, sGamma): 0 SDR, 1 HDR, 2 HDR10, 3 HLG; "" cand nu se stie."""
	s_gamma = getattr(I, "sGamma", None)
	if info is None or s_gamma is None:
		return ""
	return {0: _("No (SDR)"), 1: "HDR", 2: "HDR10", 3: "HLG"}.get(info.getInfo(s_gamma), "")


def reteaCanalului(refstr):
	"""Ce se stie despre reteaua canalului din scanarile de dinainte (Components/HdsRetele.py): {"retea", "nid", "lcn"}
	sau None (canal din afara retelelor citite, flux, modulul lipsa)."""
	try:
		from Components import HdsRetele
	except ImportError:
		return None
	try:
		return HdsRetele.pentru_ref(refstr)
	except Exception:
		return None


def randuriRetea(refstr, cuNumar=True):
	"""Randurile retelei canalului: "Rețeaua: Cablu Targu Jiu (ID 53)" si, cand operatorul ii da un numar,
	"Numărul operatorului: 23". Nimic pentru un canal fara retea stiuta."""
	r = reteaCanalului(refstr)
	if r is None:
		return []
	nume = r.get("retea") or ""
	text = (_("%s (ID %d)") % (nume, r["nid"])) if nume else (_("ID %d") % r["nid"])
	rez = [(_("Rețeaua"), text, TYPE_TEXT)]
	if cuNumar and r.get("lcn"):
		rez.append((_("Numărul operatorului"), str(r["lcn"]), TYPE_TEXT))
	return rez


def numeSiReferinta(ref, ServiceReference):
	"""(numele, referinta text) canalului de acum; fara canal, N/A."""
	if ref:
		return ServiceReference(ref).getServiceName(), ref.toString()
	return _("N/A"), _("N/A")


def randuriServiciu(info, I, nume, refstr):
	"""Rosu (Serviciu)."""
	aspect = valoare(info, I.sAspect)
	if aspect in (1, 2, 5, 6, 9, 0xA, 0xD, 0xE):
		aspect = _("4:3")
	else:
		aspect = _("16:9")
	width = info and info.getInfo(I.sVideoWidth) or -1
	height = info and info.getInfo(I.sVideoHeight) or -1
	# reteaua din scanare si numarul operatorului, langa furnizor
	retea = tuple(randuriRetea(refstr))
	if width != -1 and height != -1:
		Labels = ((_("Name"), nume, TYPE_TEXT),
			(_("Provider"), valoare(info, I.sProvider), TYPE_TEXT)) + retea + (
			(_("Aspect ratio"), aspect, TYPE_TEXT),
			(_("Resolution"), "%dx%d" % (width, height), TYPE_TEXT))
		hdr = textHdr(info, I)
		if hdr:
			Labels += ((_("HDR"), hdr, TYPE_TEXT),)
		Labels += ((_("Namespace"), valoare(info, I.sNamespace), TYPE_VALUE_HEX, 8),
			(_("Service reference"), refstr, TYPE_TEXT))
	else:
		Labels = ((_("Name"), nume, TYPE_TEXT),
			(_("Provider"), valoare(info, I.sProvider), TYPE_TEXT)) + retea + (
			(_("Aspect ratio"), aspect, TYPE_TEXT),
			(_("Namespace"), valoare(info, I.sNamespace), TYPE_VALUE_HEX, 8),
			(_("Service reference"), refstr, TYPE_TEXT))
	return list(Labels)


def randuriPid(info, I):
	"""Verde (PID-uri)."""
	return [(_("Video PID"), valoare(info, I.sVideoPID), TYPE_VALUE_HEX_DEC, 4),
		(_("Audio PID"), valoare(info, I.sAudioPID), TYPE_VALUE_HEX_DEC, 4),
		(_("PCR PID"), valoare(info, I.sPCRPID), TYPE_VALUE_HEX_DEC, 4),
		(_("PMT PID"), valoare(info, I.sPMTPID), TYPE_VALUE_HEX_DEC, 4),
		(_("TXT PID"), valoare(info, I.sTXTPID), TYPE_VALUE_HEX_DEC, 4),
		(_("TSID"), valoare(info, I.sTSID), TYPE_VALUE_HEX_DEC, 4),
		(_("ONID"), valoare(info, I.sONID), TYPE_VALUE_HEX_DEC, 4),
		(_("SID"), valoare(info, I.sSID), TYPE_VALUE_HEX_DEC, 4)]


def dateFrontend(feinfo, ref, info, centru, I):
	"""Galben (Multiplex): datele tunerului. 1. cele vii ale redarii; 2. fara tuner_type, transponderul din lista de
	canale (lamedb); 3. rezerva prin informatiile serviciului."""
	frontendData = None
	if feinfo:
		try:
			frontendData = feinfo.getAll(True)
		except Exception:
			frontendData = None
	if (not frontendData or not frontendData.get("tuner_type")) and ref:
		info_ref = centru.info(ref)
		if info_ref:
			try:
				tp_data = info_ref.getInfoObject(ref, I.sTransponderData)
				if tp_data:
					frontendData = tp_data
			except Exception:
				pass
	if (not frontendData or not frontendData.get("tuner_type")) and info:
		try:
			tp_data = info.getInfoObject(I.sTransponderData)
			if tp_data:
				frontendData = tp_data
		except Exception:
			pass
	return frontendData


def _mhz(freq, satelit):
	if satelit:
		if freq > 1000000:
			return "%d MHz" % (freq // 1000)
		if freq > 0:
			return "%d MHz" % freq
		return _("N/A")
	if freq > 1000000:
		return "%d MHz" % (freq // 1000000)
	if freq > 1000:
		return "%d MHz" % (freq // 1000)
	if freq > 0:
		return "%d MHz" % freq
	return _("N/A")


def _ksps(sr):
	if sr > 100000:
		return "%d kS/s" % (sr // 1000)
	if sr > 0:
		return "%d kS/s" % sr
	return _("N/A")


def randuriTransponder(frontendDataOrg, refstr, rec_info, ConvertToHumanReadable):
	"""Randurile multiplexului (si ale ecranului deschis cu o referinta, din lista de canale)."""
	Labels = []
	if not frontendDataOrg or not frontendDataOrg.get("tuner_type"):
		if refstr.startswith("4097:") or "://" in refstr:
			Labels.append((_("Tip transmisiune"), "IPTV / Flux Rețea IP", TYPE_TEXT))
			Labels.append((_("Protocol"), "HTTP / MPEG-TS Stream", TYPE_TEXT))
			Labels.append((_("Decodare"), "Redare software prin decodor intern", TYPE_TEXT))
			Labels.append((_("Referință serviciu"), refstr, TYPE_TEXT))
		else:
			Labels.append((_("Stare multiplex"), "Parametrii de transponder nu sunt disponibili", TYPE_TEXT))
			if rec_info["is_pc_emu"] and not rec_info["is_connected"]:
				Labels.append(("", "Conectează emulatorul la receptor (vezi tasta Albastră) pentru recepție DVB.", TYPE_TEXT))
		return Labels

	tp = ConvertToHumanReadable(frontendDataOrg)
	ttype = frontendDataOrg.get("tuner_type", "")

	# tunerul folosit
	tuner_num = frontendDataOrg.get("tuner_number")
	if tuner_num is None:
		if ttype == "DVB-S":
			tuner_num = 0
		elif ttype in ("DVB-C", "DVB-T"):
			tuner_num = 1
		else:
			# fara tuner_number si cu alt ttype, chr(65 + None) ar cadea: tunerul 0
			tuner_num = 0

	if rec_info["is_pc_emu"]:
		if rec_info["is_connected"]:
			tuner_desc = "Tuner %s (Receptor %s prin rețea)" % (chr(65 + tuner_num), rec_info["receiver_target"])
		else:
			tuner_desc = "Tuner %s virtual (Receptor neconectat)" % chr(65 + tuner_num)
	else:
		tuner_desc = "Tuner %s hardware intern" % chr(65 + tuner_num)
	Labels.append((_("Tuner recepție"), tuner_desc, TYPE_TEXT))

	if ttype == "DVB-S":
		system_str = tp.get("system", "DVB-S")
		Labels.append((_("Tip transmisie"), "Satelit (%s)" % system_str, TYPE_TEXT))
		Labels.append((_("Satelit / Poziție"), tp.get("orbital_position", _("N/A")), TYPE_TEXT))
		Labels.extend(randuriRetea(refstr, cuNumar=False))
		Labels.append((_("Frecvență"), _mhz(tp.get("frequency", 0), True), TYPE_TEXT))
		Labels.append((_("Rată simboluri (SR)"), _ksps(tp.get("symbol_rate", 0)), TYPE_TEXT))
		Labels.append((_("Polarizare"), tp.get("polarization", _("N/A")), TYPE_TEXT))
		Labels.append((_("Modulație"), tp.get("modulation", _("N/A")), TYPE_TEXT))
		Labels.append((_("FEC"), tp.get("fec_inner", _("N/A")), TYPE_TEXT))
		Labels.append((_("Inversiune"), tp.get("inversion", _("Auto")), TYPE_TEXT))
		if system_str == "DVB-S2":
			if "rolloff" in tp:
				Labels.append((_("Roll-off"), str(tp.get("rolloff")), TYPE_TEXT))
			if "pilot" in tp:
				Labels.append((_("Pilot"), str(tp.get("pilot")), TYPE_TEXT))
	elif ttype == "DVB-C":
		Labels.append((_("Tip transmisie"), "Cablu digital (DVB-C)", TYPE_TEXT))
		Labels.extend(randuriRetea(refstr, cuNumar=False))
		Labels.append((_("Frecvență"), _mhz(tp.get("frequency", 0), False), TYPE_TEXT))
		Labels.append((_("Rată simboluri (SR)"), _ksps(tp.get("symbol_rate", 0)), TYPE_TEXT))
		Labels.append((_("Modulație"), tp.get("modulation", _("N/A")), TYPE_TEXT))
		Labels.append((_("FEC"), tp.get("fec_inner", _("N/A")), TYPE_TEXT))
		Labels.append((_("Inversiune"), tp.get("inversion", _("Auto")), TYPE_TEXT))
	elif ttype == "DVB-T":
		Labels.append((_("Tip transmisie"), "Terestru digital (DVB-T/T2)", TYPE_TEXT))
		Labels.extend(randuriRetea(refstr, cuNumar=False))
		Labels.append((_("Frecvență"), _mhz(tp.get("frequency", 0), False), TYPE_TEXT))
		Labels.append((_("Lățime bandă"), tp.get("bandwidth", _("N/A")), TYPE_TEXT))
		Labels.append((_("Constelație"), tp.get("constellation", _("N/A")), TYPE_TEXT))
		Labels.append((_("Mod transmisie"), tp.get("transmission_mode", _("N/A")), TYPE_TEXT))
		Labels.append((_("Interval gardă"), tp.get("guard_interval", _("N/A")), TYPE_TEXT))
		Labels.append((_("Code rate HP"), tp.get("code_rate_hp", _("N/A")), TYPE_TEXT))
		Labels.append((_("Code rate LP"), tp.get("code_rate_lp", _("N/A")), TYPE_TEXT))
		Labels.append((_("Inversiune"), tp.get("inversion", _("Auto")), TYPE_TEXT))
	return Labels


def _procent(brut):
	return "%d %%" % (brut * 100 // 65536)


def randuriTuner(rec_info, feinfo, ref, centru, I, nimmanager, mod_receptie):
	"""Albastru (Stare tuner). `mod_receptie` = randul "Direct pe receptorul %s" deja facut de apelant (pe receptor)."""
	Labels = []
	if rec_info["is_pc_emu"]:
		if rec_info["is_connected"]:
			Labels.append((_("Conexiune tunere"), "Conectat prin rețea la receptor (DVB-TR)", TYPE_TEXT))
			# protocolul HdsTunerRetea nu trimite numele modelului, doar adresa si portul
			Labels.append((_("Receptor fizic"), "Receptor conectat prin rețea (%s)" % rec_info["receiver_target"], TYPE_TEXT))
			Labels.append((_("Tunere preluate"), ", ".join(rec_info["connected_tuners"]), TYPE_TEXT))

			# tunerul canalului de acum
			frontendData = feinfo and feinfo.getFrontendData()
			tuner_num = frontendData.get("tuner_number") if frontendData else None
			if tuner_num is None and ref:
				info = centru.info(ref)
				tp = info and info.getInfoObject(ref, I.sTransponderData)
				if tp:
					ttype = tp.get("tuner_type")
					if ttype == "DVB-S":
						tuner_num = 0
					elif ttype in ("DVB-C", "DVB-T"):
						tuner_num = 1
			if tuner_num == 0:
				canal_tuner = "Tuner A Satelit DVB-S2X (Slot 0 pe receptor)"
			elif tuner_num == 1:
				canal_tuner = "Tuner B Cablu DVB-C (Slot 1 pe receptor)"
			elif tuner_num is not None:
				canal_tuner = "Tuner %s de pe receptor" % chr(65 + tuner_num)
			else:
				canal_tuner = "Tuner DVB virtual / Redare IPTV"
			Labels.append((_("Tuner canal curent"), canal_tuner, TYPE_TEXT))
			Labels.append(("", "", TYPE_TEXT))
			Labels.append((_("Telemetrie semnal"), "Semnal recepționat live de la tunerul receptorului:", TYPE_TEXT))

			status = (feinfo and feinfo.getFrontendStatus()) or {}
			if status.get("tuner_locked"):
				lock_text = "DA (Semnal sincronizat cu succes - LOCK)"
			else:
				lock_text = "NU (Fără sincronizare / În căutare semnal)"
			Labels.append((_("Sincronizare (Lock)"), lock_text, TYPE_TEXT))
			raw_state = status.get("tuner_state", "IDLE")
			state_map = {
				"LOCKED": "Blocat pe frecvență (Recepție optimă)",
				"TUNING": "În curs de acordare...",
				"FAILED": "Lipsă semnal RF pe frecvență",
				"LOSTLOCK": "Semnal pierdut",
				"IDLE": "Inactiv / În așteptare semnal",
			}
			Labels.append((_("Stare acordare"), state_map.get(raw_state, raw_state), TYPE_TEXT))
			snr_raw = status.get("tuner_signal_quality")
			snr_db_raw = status.get("tuner_signal_quality_db")
			if snr_raw is not None and snr_raw > 0:
				if snr_db_raw is not None and snr_db_raw != 0x12345678:
					snr_str = "%s (%.2f dB)" % (_procent(snr_raw), snr_db_raw / 100.0)
				else:
					snr_str = _procent(snr_raw)
			else:
				snr_str = "0 %"
			Labels.append((_("Calitate semnal (SNR)"), snr_str, TYPE_TEXT))
			agc_raw = status.get("tuner_signal_power")
			Labels.append((_("Nivel semnal (AGC)"), _procent(agc_raw) if agc_raw is not None and agc_raw > 0 else "0 %", TYPE_TEXT))
			ber_raw = status.get("tuner_bit_error_rate")
			Labels.append((_("Rată erori (BER)"), str(ber_raw) if ber_raw is not None else "0", TYPE_TEXT))
		else:
			# emulator neconectat la receptor: pasii de conectare
			Labels.append((_("Stare conexiune"), "Receptor neconectat (Niciun tuner activ)", TYPE_TEXT))
			Labels.append((_("Mod emulator"), "Rulare autonomă pe PC (fără preluare tunere)", TYPE_TEXT))
			Labels.append(("", "-" * 96, TYPE_TEXT))
			Labels.append((_("Cum conectezi"), "Urmează pașii de mai jos pentru a prelua tunerele receptorului:", TYPE_TEXT))
			Labels.append((_("Pasul 1 (Găsire)"), "În fereastra Receptoare din rețea din bara emulatorului, apasă Caută în rețea", TYPE_TEXT))
			Labels.append(("", "  (sau apasă Adaugă după IP și introdu adresa receptorului, de ex: 192.168.1.10)", TYPE_TEXT))
			# numele receptorului: din regulile modelului cand exista, altfel cel al receptorului de azi
			try:
				from Components.About import about
				nume_receptor = about.valoareDinReguli("machinebuild") or "viper4kv20"
			except Exception:
				nume_receptor = "viper4kv20"
			Labels.append((_("Pasul 2 (Listă)"), "Receptorul %s va apărea în tabel cu starea Cere împerechere" % nume_receptor, TYPE_TEXT))
			Labels.append((_("Pasul 3 (Împerechere)"), "Dă clic pe rândul receptorului din listă, apoi apasă butonul Împerechează", TYPE_TEXT))
			Labels.append((_("Pasul 4 (Cod PIN)"), "Pe ecranul televizorului va apărea un cod PIN de 6 cifre. Scrie PIN-ul pe PC și apasă OK", TYPE_TEXT))
			Labels.append((_("Pasul 5 (Tunere)"), "Apasă Alege tunerele și bifează: Tuner A (Satelit DVB-S2X) și/sau Tuner B (Cablu DVB-C)", TYPE_TEXT))
			Labels.append((_("Pasul 6 (Pornire)"), "Apasă Folosește în emulator. Tunerele receptorului vor fi conectate instantaneu prin rețea.", TYPE_TEXT))
	else:
		# direct pe receptor: numele receptorului (about.getReceiverName, dat de apelant) si descrierile reale ale
		# tunerelor, raportate de driver (nimmanager.getNimDescription)
		Labels.append((_("Mod recepție"), mod_receptie, TYPE_TEXT))
		nume_sloturi = [_("Tuner A"), _("Tuner B"), _("Tuner C"), _("Tuner D")]
		for idx in range(min(nimmanager.getSlotCount(), len(nume_sloturi))):
			try:
				descriere = nimmanager.getNimDescription(idx)
			except Exception:
				descriere = ""
			if descriere:
				Labels.append((nume_sloturi[idx], descriere, TYPE_TEXT))
		status = (feinfo and feinfo.getFrontendStatus()) or {}
		locked = status.get("tuner_locked")
		Labels.append((_("Sincronizare (Lock)"), "DA (LOCK)" if locked else "NU (Fără semnal)", TYPE_TEXT))
		snr_raw = status.get("tuner_signal_quality")
		Labels.append((_("Calitate semnal (SNR)"), _procent(snr_raw) if snr_raw is not None else "0 %", TYPE_TEXT))
		agc_raw = status.get("tuner_signal_power")
		Labels.append((_("Nivel semnal (AGC)"), _procent(agc_raw) if agc_raw is not None else "0 %", TYPE_TEXT))
		ber_raw = status.get("tuner_bit_error_rate")
		Labels.append((_("Rată erori (BER)"), str(ber_raw) if ber_raw is not None else "0", TYPE_TEXT))
	return Labels
