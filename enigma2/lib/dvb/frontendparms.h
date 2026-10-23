/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_dvb_frontendparms_h
#define __lib_dvb_frontendparms_h

#include <lib/python/swig.h>

class SatelliteDeliverySystemDescriptor;
class CableDeliverySystemDescriptor;
class TerrestrialDeliverySystemDescriptor;

struct eDVBFrontendParametersSatellite
{
#ifndef SWIG
	void set(const SatelliteDeliverySystemDescriptor  &);
#endif
	enum {
		Polarisation_Horizontal, Polarisation_Vertical, Polarisation_CircularLeft, Polarisation_CircularRight
	};

	enum {
		Inversion_Off, Inversion_On, Inversion_Unknown
	};

	enum {
		FEC_Auto, FEC_1_2, FEC_2_3, FEC_3_4, FEC_5_6, FEC_7_8, FEC_8_9, FEC_3_5, FEC_4_5, FEC_9_10, FEC_None=15
	};

	enum {
		System_DVB_S, System_DVB_S2
	};

	enum {
		Modulation_Auto, Modulation_QPSK, Modulation_8PSK, Modulation_QAM16
	};

	// dvb-s2
	enum {
		RollOff_alpha_0_35, RollOff_alpha_0_25, RollOff_alpha_0_20
	};

	enum {
		Pilot_Off, Pilot_On, Pilot_Unknown
	};

	// multistream DVB-S2 (lib/dvb/hdsmultistream.h): is_id 0..255 sau No_Stream_Id_Filter, pls_mode, pls_code pe 18 biti;
	// t2mi_plp_id / t2mi_pid sunt numai date (lamedb, satellites.xml, afisare), nu se trimit driverului
	enum {
		No_Stream_Id_Filter = -1
	};

	enum {
		PLS_Root, PLS_Gold, PLS_Combo
	};

	enum {
		No_T2MI_PLP_Id = -1, T2MI_Default_Pid = 4096
	};

	bool no_rotor_command_on_tune;
	unsigned int frequency, symbol_rate;
	int polarisation, fec, inversion, orbital_position, system, modulation, rolloff, pilot;
	int is_id, pls_mode, pls_code, t2mi_plp_id, t2mi_pid;

#ifndef SWIG
	// structura ramane fara constructor (sta in uniuni: eDVBFrontendParameters, eDVBFrontend::oparm), deci orice loc
	// care o face din nou cheama aceasta functie; obiectele facute din Python primesc aceleasi valori din %extend
	void setMultistreamDefaults()
	{
		is_id = No_Stream_Id_Filter;
		pls_mode = PLS_Gold;
		pls_code = 0;
		t2mi_plp_id = No_T2MI_PLP_Id;
		t2mi_pid = T2MI_Default_Pid;
	}
	// filtrul de flux sau o secventa PLS: numai atunci primeste driverul DTV_STREAM_ID
	bool needsStreamSelection() const;
#endif
};
#ifdef SWIG
%extend eDVBFrontendParametersSatellite {
	eDVBFrontendParametersSatellite()
	{
		eDVBFrontendParametersSatellite *p = new eDVBFrontendParametersSatellite();
		p->is_id = eDVBFrontendParametersSatellite::No_Stream_Id_Filter;
		p->pls_mode = eDVBFrontendParametersSatellite::PLS_Gold;
		p->pls_code = 0;
		p->t2mi_plp_id = eDVBFrontendParametersSatellite::No_T2MI_PLP_Id;
		p->t2mi_pid = eDVBFrontendParametersSatellite::T2MI_Default_Pid;
		return p;
	}
}
#endif
SWIG_ALLOW_OUTPUT_SIMPLE(eDVBFrontendParametersSatellite);

struct eDVBFrontendParametersCable
{
#ifndef SWIG
	void set(const CableDeliverySystemDescriptor  &);
#endif
	enum {
		Inversion_Off, Inversion_On, Inversion_Unknown
	};

	enum {
		FEC_Auto, FEC_1_2, FEC_2_3, FEC_3_4, FEC_5_6, FEC_7_8, FEC_8_9, FEC_None=15
	};

	enum {
		Modulation_Auto, Modulation_QAM16, Modulation_QAM32, Modulation_QAM64, Modulation_QAM128, Modulation_QAM256
	};

	unsigned int frequency, symbol_rate;
	int modulation, inversion, fec_inner;
};
SWIG_ALLOW_OUTPUT_SIMPLE(eDVBFrontendParametersCable);

struct eDVBFrontendParametersTerrestrial
{
#ifndef SWIG
	void set(const TerrestrialDeliverySystemDescriptor  &);
#endif
	enum {
		Bandwidth_8MHz, Bandwidth_7MHz, Bandwidth_6MHz, /*Bandwidth_5MHz,*/ Bandwidth_Auto
	}; // Bw5Mhz nyi (compatibilty with enigma1)

	enum {
		FEC_1_2, FEC_2_3, FEC_3_4, FEC_5_6, FEC_7_8, FEC_Auto
	};

	enum {
		TransmissionMode_2k, TransmissionMode_8k, /*TransmissionMode_4k,*/ TransmissionMode_Auto
	}; // TM4k nyi (compatibility with enigma1)

	enum {
		GuardInterval_1_32, GuardInterval_1_16, GuardInterval_1_8, GuardInterval_1_4, GuardInterval_Auto
	};

	enum {
		Hierarchy_None, Hierarchy_1, Hierarchy_2, Hierarchy_4, Hierarchy_Auto
	};

	enum {
		Modulation_QPSK, Modulation_QAM16, Modulation_QAM64, Modulation_Auto
	};

	enum {
		Inversion_Off, Inversion_On, Inversion_Unknown
	};

	unsigned int frequency;
	int bandwidth;
	int code_rate_HP, code_rate_LP;
	int modulation;
	int transmission_mode;
	int guard_interval;
	int hierarchy;
	int inversion;
};
SWIG_ALLOW_OUTPUT_SIMPLE(eDVBFrontendParametersTerrestrial);

#endif
