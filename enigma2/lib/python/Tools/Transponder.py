# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eDVBFrontendParametersSatellite, eDVBFrontendParametersCable, eDVBFrontendParametersTerrestrial
from Components.NimManager import nimmanager

def ConvertToHumanReadable(tp, type = None):
	ret = { }
	if type is None:
		type = tp.get("tuner_type", "None")
	if type == "DVB-S":
		ret["tuner_type"] = _("Satellite")
		ret["inversion"] = {
			eDVBFrontendParametersSatellite.Inversion_Unknown : _("Auto"),
			eDVBFrontendParametersSatellite.Inversion_On : _("On"),
			eDVBFrontendParametersSatellite.Inversion_Off : _("Off")}[tp["inversion"]]
		ret["fec_inner"] = {
			eDVBFrontendParametersSatellite.FEC_None : _("None"),
			eDVBFrontendParametersSatellite.FEC_Auto : _("Auto"),
			eDVBFrontendParametersSatellite.FEC_1_2 : "1/2",
			eDVBFrontendParametersSatellite.FEC_2_3 : "2/3",
			eDVBFrontendParametersSatellite.FEC_3_4 : "3/4",
			eDVBFrontendParametersSatellite.FEC_5_6 : "5/6",
			eDVBFrontendParametersSatellite.FEC_7_8 : "7/8",
			eDVBFrontendParametersSatellite.FEC_3_5 : "3/5",
			eDVBFrontendParametersSatellite.FEC_4_5 : "4/5",
			eDVBFrontendParametersSatellite.FEC_8_9 : "8/9",
			eDVBFrontendParametersSatellite.FEC_9_10 : "9/10"}[tp["fec_inner"]]
		ret["modulation"] = {
			eDVBFrontendParametersSatellite.Modulation_Auto : _("Auto"),
			eDVBFrontendParametersSatellite.Modulation_QPSK : "QPSK",
			eDVBFrontendParametersSatellite.Modulation_QAM16 : "QAM16",
			eDVBFrontendParametersSatellite.Modulation_8PSK : "8PSK"}[tp["modulation"]]
		ret["orbital_position"] = nimmanager.getSatName(int(tp["orbital_position"]))
		ret["polarization"] = {
			eDVBFrontendParametersSatellite.Polarisation_Horizontal : _("Horizontal"),
			eDVBFrontendParametersSatellite.Polarisation_Vertical : _("Vertical"),
			eDVBFrontendParametersSatellite.Polarisation_CircularLeft : _("Circular left"),
			eDVBFrontendParametersSatellite.Polarisation_CircularRight : _("Circular right")}[tp["polarization"]]
		ret["system"] = {
			eDVBFrontendParametersSatellite.System_DVB_S : "DVB-S",
			eDVBFrontendParametersSatellite.System_DVB_S2 : "DVB-S2"}[tp["system"]]
		if ret["system"] == "DVB-S2":
			ret["rolloff"] = {
				eDVBFrontendParametersSatellite.RollOff_alpha_0_35 : "0.35",
				eDVBFrontendParametersSatellite.RollOff_alpha_0_25 : "0.25",
				eDVBFrontendParametersSatellite.RollOff_alpha_0_20 : "0.20"}[tp["rolloff"]]
			ret["pilot"] = {
				eDVBFrontendParametersSatellite.Pilot_Unknown : _("Auto"),
				eDVBFrontendParametersSatellite.Pilot_On : _("On"),
				eDVBFrontendParametersSatellite.Pilot_Off : _("Off")}[tp["pilot"]]
	elif type == "DVB-C":
		ret["tuner_type"] = _("Cable")
		ret["modulation"] = {
			eDVBFrontendParametersCable.Modulation_Auto: _("Auto"),
			eDVBFrontendParametersCable.Modulation_QAM16 : "QAM16",
			eDVBFrontendParametersCable.Modulation_QAM32 : "QAM32",
			eDVBFrontendParametersCable.Modulation_QAM64 : "QAM64",
			eDVBFrontendParametersCable.Modulation_QAM128 : "QAM128",
			eDVBFrontendParametersCable.Modulation_QAM256 : "QAM256"}[tp["modulation"]]
		ret["inversion"] = {
			eDVBFrontendParametersCable.Inversion_Unknown : _("Auto"),
			eDVBFrontendParametersCable.Inversion_On : _("On"),
			eDVBFrontendParametersCable.Inversion_Off : _("Off")}[tp["inversion"]]
		ret["fec_inner"] = {
			eDVBFrontendParametersCable.FEC_None : _("None"),
			eDVBFrontendParametersCable.FEC_Auto : _("Auto"),
			eDVBFrontendParametersCable.FEC_1_2 : "1/2",
			eDVBFrontendParametersCable.FEC_2_3 : "2/3",
			eDVBFrontendParametersCable.FEC_3_4 : "3/4",
			eDVBFrontendParametersCable.FEC_5_6 : "5/6",
			eDVBFrontendParametersCable.FEC_7_8 : "7/8",
			eDVBFrontendParametersCable.FEC_8_9 : "8/9"}[tp["fec_inner"]]
	elif type == "DVB-T":
		# valorile DVB-T2 (256QAM, 1/128, 32k...) sunt in structura dupa Auto; o valoare necunoscuta se arata ca numar,
		# nu opreste ecranul
		T = eDVBFrontendParametersTerrestrial
		def text(cheie, tabel):
			v = tp.get(cheie)
			return tabel.get(v, str(v))
		t2 = tp.get("system") == T.System_DVB_T2
		ret["tuner_type"] = _("Terrestrial")
		ret["system"] = "DVB-T2" if t2 else "DVB-T"
		ret["plp_id"] = (str(tp["plp_id"]) if t2 and tp.get("plp_id", -1) >= 0 else _("Auto"))
		ret["bandwidth"] = text("bandwidth", {
			T.Bandwidth_Auto : _("Auto"),
			T.Bandwidth_8MHz : "8 MHz",
			T.Bandwidth_7MHz : "7 MHz",
			T.Bandwidth_6MHz : "6 MHz",
			T.Bandwidth_5MHz : _("5 MHz"),
			T.Bandwidth_10MHz : _("10 MHz"),
			T.Bandwidth_1_712MHz : "1,712 MHz"})
		fec = {
			T.FEC_Auto : _("Auto"),
			T.FEC_1_2 : "1/2",
			T.FEC_2_3 : "2/3",
			T.FEC_3_4 : "3/4",
			T.FEC_5_6 : "5/6",
			T.FEC_7_8 : "7/8",
			T.FEC_8_9 : "8/9",
			T.FEC_3_5 : "3/5",
			T.FEC_4_5 : "4/5"}
		ret["code_rate_lp"] = text("code_rate_lp", fec)
		ret["code_rate_hp"] = text("code_rate_hp", fec)
		ret["constellation"] = text("constellation", {
			T.Modulation_Auto : _("Auto"),
			T.Modulation_QPSK : "QPSK",
			T.Modulation_QAM16 : "QAM16",
			T.Modulation_QAM64 : "QAM64",
			T.Modulation_QAM256 : "QAM256"})
		ret["transmission_mode"] = text("transmission_mode", {
			T.TransmissionMode_Auto : _("Auto"),
			T.TransmissionMode_1k : "1k",
			T.TransmissionMode_2k : "2k",
			T.TransmissionMode_4k : "4k",
			T.TransmissionMode_8k : "8k",
			T.TransmissionMode_16k : "16k",
			T.TransmissionMode_32k : "32k"})
		ret["guard_interval"] = text("guard_interval", {
			T.GuardInterval_Auto : _("Auto"),
			T.GuardInterval_1_32 : "1/32",
			T.GuardInterval_1_16 : "1/16",
			T.GuardInterval_1_8 : "1/8",
			T.GuardInterval_1_4 : "1/4",
			T.GuardInterval_1_128 : "1/128",
			T.GuardInterval_19_128 : "19/128",
			T.GuardInterval_19_256 : "19/256"})
		ret["hierarchy_information"] = text("hierarchy_information", {
			T.Hierarchy_Auto : _("Auto"),
			T.Hierarchy_None : _("None"),
			T.Hierarchy_1 : "1",
			T.Hierarchy_2 : "2",
			T.Hierarchy_4 : "4"})
		ret["inversion"] = text("inversion", {
			T.Inversion_Unknown : _("Auto"),
			T.Inversion_On : _("On"),
			T.Inversion_Off : _("Off")})
	else:
		print("ConvertToHumanReadable: no or unknown type in tpdata dict!")
	for x in list(tp.keys()):
		if x not in ret:
			ret[x] = tp[x]
	return ret
