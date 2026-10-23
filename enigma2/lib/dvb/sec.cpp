/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/dvb/dvb.h>
#include <lib/dvb/sec.h>
#include <lib/dvb/rotor_calc.h>
#include <lib/dvb/dvbtime.h>
#include <lib/dvb/hdsurmamotor.h>
#include <lib/dvb/hdsrotire.h>

#include <set>
#include <time.h>
#include <string.h>

#if HAVE_DVB_API_VERSION < 3
#define FREQUENCY Frequency
#else
#define FREQUENCY frequency
#endif
#include <lib/base/eerror.h>

//#define SEC_DEBUG

#ifdef SEC_DEBUG
#define eSecDebug(arg...) eDebug(arg)
#else
#define eSecDebug(arg...)
#endif

DEFINE_REF(eDVBSatelliteEquipmentControl);

eDVBSatelliteEquipmentControl *eDVBSatelliteEquipmentControl::instance;

int eDVBSatelliteEquipmentControl::m_params[MAX_PARAMS];
/*
   defaults are set in python lib/python/Components/NimManager.py
   in InitSecParams function via setParam call
*/

void eDVBSatelliteEquipmentControl::setParam(int param, int value)
{
	if (param >= 0 && param < MAX_PARAMS)
		m_params[param]=value;
}

eDVBSatelliteEquipmentControl::eDVBSatelliteEquipmentControl(eSmartPtrList<eDVBRegisteredFrontend> &avail_frontends, eSmartPtrList<eDVBRegisteredFrontend> &avail_simulate_frontends)
	:m_lnbidx((sizeof(m_lnbs) / sizeof(eDVBSatelliteLNBParameters))-1), m_curSat(m_lnbs[0].m_satellites.end()), m_avail_frontends(avail_frontends), m_avail_simulate_frontends(avail_simulate_frontends), m_rotorMoving(0)
{
	if (!instance)
		instance = this;
	memset(m_hds_rotor, 0, sizeof(m_hds_rotor));
	clear();
}

#define eSecDebugNoSimulate(x...) \
	do { \
		if (!simulate) \
			eSecDebug(x); \
	} while(0)
//		else
//		{
//			eDebugNoNewLine("SIMULATE:");
//			eDebug(x);
//		}

int eDVBSatelliteEquipmentControl::canTune(const eDVBFrontendParametersSatellite &sat, iDVBFrontend *fe, int slot_id, int *highest_score_lnb)
{
	bool simulate = ((eDVBFrontend*)fe)->is_simulate();
	bool direct_connected = m_not_linked_slot_mask & slot_id;
	int score=0, satcount=0;
	long linked_prev_ptr=-1, linked_next_ptr=-1, linked_csw=-1, linked_ucsw=-1, linked_toneburst=-1,
		fe_satpos_depends_ptr=-1, fe_rotor_pos=-1;
	bool linked_in_use = false;

	eSecDebugNoSimulate("direct_connected %d", !!direct_connected);

	fe->getData(eDVBFrontend::LINKED_PREV_PTR, linked_prev_ptr);
	fe->getData(eDVBFrontend::LINKED_NEXT_PTR, linked_next_ptr);
	fe->getData(eDVBFrontend::SATPOS_DEPENDS_PTR, fe_satpos_depends_ptr);

	// first we search the linkage base frontend and check if any tuner in prev direction is used
	while (linked_prev_ptr != -1)
	{
		eDVBRegisteredFrontend *linked_fe = (eDVBRegisteredFrontend*) linked_prev_ptr;
		if (linked_fe->m_inuse)
			linked_in_use = true;
		fe = linked_fe->m_frontend;
		linked_fe->m_frontend->getData(eDVBFrontend::LINKED_PREV_PTR, (long&)linked_prev_ptr);
	}

	fe->getData(eDVBFrontend::ROTOR_POS, fe_rotor_pos);

	// now check also the linked tuners  is in use
	while (!linked_in_use && linked_next_ptr != -1)
	{
		eDVBRegisteredFrontend *linked_fe = (eDVBRegisteredFrontend*) linked_next_ptr;
		if (linked_fe->m_inuse)
			linked_in_use = true;
		linked_fe->m_frontend->getData(eDVBFrontend::LINKED_NEXT_PTR, (long&)linked_next_ptr);
	}

	// when a linked in use tuner is found we get the tuner data...
	if (linked_in_use)
	{
		fe->getData(eDVBFrontend::CSW, linked_csw);
		fe->getData(eDVBFrontend::UCSW, linked_ucsw);
		fe->getData(eDVBFrontend::TONEBURST, linked_toneburst);
	}

	if (highest_score_lnb)
		*highest_score_lnb = -1;

	eSecDebugNoSimulate("canTune %d", slot_id);

	for (int idx=0; idx <= m_lnbidx; ++idx )
	{
		bool rotor=false;
		eDVBSatelliteLNBParameters &lnb_param = m_lnbs[idx];
		bool is_unicable = lnb_param.SatCR_idx != -1;
		bool is_unicable_position_switch = lnb_param.SatCR_positions > 1;

		if ( lnb_param.m_slot_mask & slot_id ) // lnb for correct tuner?
		{
			int ret = 0;
			eDVBSatelliteDiseqcParameters &di_param = lnb_param.m_diseqc_parameters;

			eSecDebugNoSimulate("lnb %d found", idx);

			satcount += lnb_param.m_satellites.size();

			std::map<int, eDVBSatelliteSwitchParameters>::iterator sit =
				lnb_param.m_satellites.find(sat.orbital_position);
			if ( sit != lnb_param.m_satellites.end())
			{
				bool diseqc=false;
				long band=0,
					satpos_depends_ptr=fe_satpos_depends_ptr,
					csw = di_param.m_committed_cmd,
					ucsw = di_param.m_uncommitted_cmd,
					toneburst = di_param.m_toneburst_param,
					rotor_pos = fe_rotor_pos;

				eSecDebugNoSimulate("sat %d found", sat.orbital_position);

				if ( sat.frequency > lnb_param.m_lof_threshold )
					band |= 1;
				if (!(sat.polarisation & eDVBFrontendParametersSatellite::Polarisation_Vertical))
					band |= 2;

				if (di_param.m_diseqc_mode >= eDVBSatelliteDiseqcParameters::V1_0)
				{
					diseqc=true;
					if ( di_param.m_committed_cmd < eDVBSatelliteDiseqcParameters::SENDNO )
						csw = 0xF0 | (csw << 2);

					if (di_param.m_committed_cmd <= eDVBSatelliteDiseqcParameters::SENDNO)
						csw |= band;

					if ( di_param.m_diseqc_mode == eDVBSatelliteDiseqcParameters::V1_2 )  // ROTOR
						rotor = true;

					ret = 10000;
				}
				else
				{
					csw = band;
					ret = 15000;
				}

				if (sat.no_rotor_command_on_tune && !rotor) {
					eSecDebugNoSimulate("no rotor but no_rotor_command_on_tune is set.. ignore lnb %d", idx);
					continue;
				}

				eSecDebugNoSimulate("ret1 %d", ret);

				if (linked_in_use && !is_unicable)
				{
					// compare tuner data
					if ( (csw != linked_csw) ||
						( diseqc && (ucsw != linked_ucsw || toneburst != linked_toneburst) ) ||
						( rotor && rotor_pos != sat.orbital_position ) )
					{
						ret = 0;
					}
					else
						ret += 15;
					eSecDebugNoSimulate("ret2 %d", ret);
				}
				else if ((satpos_depends_ptr != -1) && !(is_unicable && is_unicable_position_switch))
				{
					eSecDebugNoSimulate("satpos depends");
					eDVBRegisteredFrontend *satpos_depends_to_fe = (eDVBRegisteredFrontend*) satpos_depends_ptr;
					if (direct_connected) // current fe is direct connected.. (can turn the rotor)
					{
						if (satpos_depends_to_fe->m_inuse) // if the dependent frontend is in use?
						{
							if (!rotor || rotor_pos != sat.orbital_position) // new orbital position not equal to current orbital pos?
								ret = 0;
							else
								ret += 10;
						}
						eSecDebugNoSimulate("ret3 %d", ret);
					}
					else // current fe is dependent of another tuner ... (so this fe can't turn the rotor!)
					{
						// get current orb pos of the tuner with rotor connection
						satpos_depends_to_fe->m_frontend->getData(eDVBFrontend::ROTOR_POS, rotor_pos);
						if (!rotor || rotor_pos == -1 /* we dont know the rotor position yet */
							|| rotor_pos != sat.orbital_position ) // not the same orbital position?
						{
							ret = 0;
						}
					}
					eSecDebugNoSimulate("ret4 %d", ret);
				}

				if (ret && rotor && rotor_pos != -1)
					ret -= abs(rotor_pos-sat.orbital_position);

				eSecDebugNoSimulate("ret5 %d", ret);

				if (ret && !is_unicable)
				{
					int lof = sat.frequency > lnb_param.m_lof_threshold ?
						lnb_param.m_lof_hi : lnb_param.m_lof_lo;
					int tuner_freq = abs((int)sat.frequency - lof);
					if (tuner_freq < 900000 || tuner_freq > 2200000)
						ret = 0;
				}

				if (ret && lnb_param.m_prio != -1)
					ret = lnb_param.m_prio;

				eSecDebugNoSimulate("ret %d, score old %d", ret, score);
				if (ret > score)
				{
					score = ret;
					if (highest_score_lnb)
						*highest_score_lnb = idx;
				}
				eSecDebugNoSimulate("score new %d", score);
			}
		}
	}
	if (score && satcount)
	{
		if (score > (satcount-1))
			score -= (satcount-1);
		else
			score = 1; // min score
	}
	if (score && direct_connected)
		score += 5; // increase score for tuners with direct sat connection
	eSecDebugNoSimulate("final score %d", score);
	return score;
}

bool need_turn_fast(int turn_speed)
{
	if (turn_speed == eDVBSatelliteRotorParameters::FAST)
		return true;
	else if (turn_speed != eDVBSatelliteRotorParameters::SLOW)
	{
		int begin = turn_speed >> 16; // high word is start time
		int end = turn_speed&0xFFFF; // low word is end time
		time_t now_time = ::time(0);
		tm nowTime;
		localtime_r(&now_time, &nowTime);
		int now = (nowTime.tm_hour + 1) * 60 + nowTime.tm_min + 1;
		bool neg = end <= begin;
		if (neg) {
			int tmp = begin;
			begin = end;
			end = tmp;
		}
		if ((now >= begin && now < end) ^ neg)
			return true;
	}
	return false;
}

#define VOLTAGE(x) (lnb_param.m_increased_voltage ? iDVBFrontend::voltage##x##_5 : iDVBFrontend::voltage##x)

/* HDSatelit (lib/dvb/hdsrotire.h): modelul motorului pus din Python (cheia = slotul tunerului) si
   zona in care poate fi antena cand nucleul nu-i stie pozitia (capetele unei mutari intrerupte; cheia = slotul
   radacinii lantului de tunere, unde stau ROTOR_POS si ROTOR_CMD). Nucleul are un singur
   eDVBSatelliteEquipmentControl. */
static hdsrotire::Model s_hds_model[HDS_MAX_ROTOR_SLOTS];
static hdsrotire::Zona s_hds_zona[HDS_MAX_ROTOR_SLOTS];
/* transponderele satelitilor motorului, puse din Python (cheia = slotul tunerului; raman si dupa clear(), ca
   satellites.xml), si ceasul probei de semnal in curs (cheia = slotul tunerului care acordeaza) */
static hdsrotire::Transpondere s_hds_tp[HDS_MAX_ROTOR_SLOTS];
static long long s_hds_proba_ms[HDS_MAX_ROTOR_SLOTS];

static const hdsrotire::Model &hdsModelMotor(int slot, int radacina)
{
	static const hdsrotire::Model presupus;
	if (slot >= 0 && slot < HDS_MAX_ROTOR_SLOTS && s_hds_model[slot].pus)
		return s_hds_model[slot];
	if (radacina >= 0 && radacina < HDS_MAX_ROTOR_SLOTS && s_hds_model[radacina].pus)
		return s_hds_model[radacina];
	return presupus;
}

static const hdsrotire::Transpondere &hdsTranspondereMotor(int slot, int radacina)
{
	static const hdsrotire::Transpondere nepuse;
	if (slot >= 0 && slot < HDS_MAX_ROTOR_SLOTS && s_hds_tp[slot].pusa)
		return s_hds_tp[slot];
	if (radacina >= 0 && radacina < HDS_MAX_ROTOR_SLOTS && s_hds_tp[radacina].pusa)
		return s_hds_tp[radacina];
	return nepuse;
}

#define eDebugNoSimulate(x...) \
	do { \
		if (!simulate) \
			eDebug(x); \
	} while(0)
//		else
//		{
//			eDebugNoNewLine("SIMULATE:");
//			eDebug(x);
//		}

RESULT eDVBSatelliteEquipmentControl::prepare(iDVBFrontend &frontend, FRONTENDPARAMETERS &parm, const eDVBFrontendParametersSatellite &sat, int slot_id, unsigned int tunetimeout)
{
	bool simulate = ((eDVBFrontend*)&frontend)->is_simulate();
	int lnb_idx = -1;
	if (canTune(sat, &frontend, slot_id, &lnb_idx))
	{
		eDVBSatelliteLNBParameters &lnb_param = m_lnbs[lnb_idx];
		eDVBSatelliteDiseqcParameters &di_param = lnb_param.m_diseqc_parameters;
		eDVBSatelliteRotorParameters &rotor_param = lnb_param.m_rotor_parameters;

		std::map<int, eDVBSatelliteSwitchParameters>::iterator sit =
			lnb_param.m_satellites.find(sat.orbital_position);
		if ( sit != lnb_param.m_satellites.end())
		{
			eSecCommandList sec_sequence;
			eDVBSatelliteSwitchParameters &sw_param = sit->second;
			bool doSetFrontend = true;
			bool doSetVoltageToneFrontend = true;
			bool forceChanged = false;
			bool needDiSEqCReset = false;
			long band=0,
				voltage = iDVBFrontend::voltageOff,
				tone = iDVBFrontend::toneOff,
				csw = di_param.m_committed_cmd,
				ucsw = di_param.m_uncommitted_cmd,
				toneburst = di_param.m_toneburst_param,
				lastcsw = -1,
				lastucsw = -1,
				lastToneburst = -1,
				lastRotorCmd = -1,
				curRotorPos = -1,
				satposDependPtr = -1;
			iDVBFrontend *sec_fe=&frontend;
			eDVBRegisteredFrontend *linked_fe = 0;
			eDVBSatelliteDiseqcParameters::t_diseqc_mode diseqc_mode = di_param.m_diseqc_mode;
			eDVBSatelliteSwitchParameters::t_voltage_mode voltage_mode = sw_param.m_voltage_mode;
			bool diseqc13V = voltage_mode == eDVBSatelliteSwitchParameters::HV_13;
			bool is_unicable = lnb_param.SatCR_idx != -1;

			bool useGotoXX = false;
			int RotorCmd=-1;
			int send_mask = 0;

			lnb_param.guard_offset = 0; //HACK

			frontend.setData(eDVBFrontend::SATCR, lnb_param.SatCR_idx);

			if (diseqc13V)
				voltage_mode = eDVBSatelliteSwitchParameters::HV;

			frontend.getData(eDVBFrontend::SATPOS_DEPENDS_PTR, satposDependPtr);

			if (!(m_not_linked_slot_mask & slot_id))  // frontend with direct connection?
			{
				long linked_prev_ptr;
				frontend.getData(eDVBFrontend::LINKED_PREV_PTR, linked_prev_ptr);
				while (linked_prev_ptr != -1)
				{
					linked_fe = (eDVBRegisteredFrontend*) linked_prev_ptr;
					sec_fe = linked_fe->m_frontend;
					sec_fe->getData(eDVBFrontend::LINKED_PREV_PTR, (long&)linked_prev_ptr);
				}
				if (satposDependPtr != -1)  // we dont need uncommitted switch and rotor cmds on second output of a rotor lnb
					diseqc_mode = eDVBSatelliteDiseqcParameters::V1_0;
				else {
					// in eDVBFrontend::tuneLoop we call closeFrontend and ->inc_use() in this this condition (to put the kernel frontend thread into idle state)
					// so we must resend all diseqc stuff (voltage is disabled when the frontend is closed)
					int state;
					sec_fe->getState(state);
					if (!linked_fe->m_inuse && state != eDVBFrontend::stateIdle)
						forceChanged = true;
				}
			}

			sec_fe->getData(eDVBFrontend::CSW, lastcsw);
			sec_fe->getData(eDVBFrontend::UCSW, lastucsw);
			sec_fe->getData(eDVBFrontend::TONEBURST, lastToneburst);
			sec_fe->getData(eDVBFrontend::ROTOR_CMD, lastRotorCmd);
			sec_fe->getData(eDVBFrontend::ROTOR_POS, curRotorPos);

			if (lastcsw == lastucsw && lastToneburst == lastucsw && lastucsw == -1)
				needDiSEqCReset = true;

			if ( sat.frequency > lnb_param.m_lof_threshold )
				band |= 1;
			if (!(sat.polarisation & eDVBFrontendParametersSatellite::Polarisation_Vertical))
				band |= 2;

			int lof = (band&1)?lnb_param.m_lof_hi:lnb_param.m_lof_lo;

			if(!is_unicable)
			{
				// calc Frequency
				int local= abs((int)sat.frequency
					- lof);
				parm.FREQUENCY = ((((local * 2) / 125) + 1) / 2) * 125;
				frontend.setData(eDVBFrontend::FREQ_OFFSET, sat.frequency - parm.FREQUENCY);

				if ( voltage_mode == eDVBSatelliteSwitchParameters::_14V
					|| ( sat.polarisation & eDVBFrontendParametersSatellite::Polarisation_Vertical
						&& voltage_mode == eDVBSatelliteSwitchParameters::HV )  )
					voltage = VOLTAGE(13);
				else if ( voltage_mode == eDVBSatelliteSwitchParameters::_18V
					|| ( !(sat.polarisation & eDVBFrontendParametersSatellite::Polarisation_Vertical)
						&& voltage_mode == eDVBSatelliteSwitchParameters::HV )  )
					voltage = VOLTAGE(18);
				if ( (sw_param.m_22khz_signal == eDVBSatelliteSwitchParameters::ON)
					|| ( sw_param.m_22khz_signal == eDVBSatelliteSwitchParameters::HILO && (band&1) ) )
					tone = iDVBFrontend::toneOn;
				else if ( (sw_param.m_22khz_signal == eDVBSatelliteSwitchParameters::OFF)
					|| ( sw_param.m_22khz_signal == eDVBSatelliteSwitchParameters::HILO && !(band&1) ) )
					tone = iDVBFrontend::toneOff;
			}
			else
			{
				int tmp1 = abs((int)sat.frequency
						-lof)
						+ lnb_param.SatCRvco
						- 1400000
						+ lnb_param.guard_offset;
				int tmp2 = ((((tmp1 * 2) / 4000) + 1) / 2) * 4000;
				parm.FREQUENCY = lnb_param.SatCRvco - (tmp1-tmp2) + lnb_param.guard_offset;
				lnb_param.UnicableTuningWord = ((tmp2 / 4000) 
						| ((band & 1) ? 0x400 : 0)			//HighLow
						| ((band & 2) ? 0x800 : 0)			//VertHor
						| ((lnb_param.LNBNum & 1) ? 0 : 0x1000)			//Umschaltung LNB1 LNB2
						| (lnb_param.SatCR_idx << 13));		//Adresse des SatCR
						eDebug("[prepare] UnicableTuningWord %#04x",lnb_param.UnicableTuningWord);
						eDebug("[prepare] guard_offset %d",lnb_param.guard_offset);
				frontend.setData(eDVBFrontend::FREQ_OFFSET, (lnb_param.UnicableTuningWord & 0x3FF) *4000 + 1400000 + lof - (2 * (lnb_param.SatCRvco - (tmp1-tmp2))) );
				voltage = VOLTAGE(13);
			}

			if (diseqc_mode >= eDVBSatelliteDiseqcParameters::V1_0)
			{
				if ( di_param.m_committed_cmd < eDVBSatelliteDiseqcParameters::SENDNO )
					csw = 0xF0 | (csw << 2);

				if (di_param.m_committed_cmd <= eDVBSatelliteDiseqcParameters::SENDNO)
					csw |= band;

				bool send_csw =
					(di_param.m_committed_cmd != eDVBSatelliteDiseqcParameters::SENDNO);
				bool changed_csw = send_csw && (forceChanged || csw != lastcsw);

				bool send_ucsw =
					(di_param.m_uncommitted_cmd && diseqc_mode > eDVBSatelliteDiseqcParameters::V1_0);
				bool changed_ucsw = send_ucsw && (forceChanged || ucsw != lastucsw);

				bool send_burst =
					(di_param.m_toneburst_param != eDVBSatelliteDiseqcParameters::NO);
				bool changed_burst = send_burst && (forceChanged || toneburst != lastToneburst);

				/* send_mask
					1 must send csw
					2 must send ucsw
					4 send toneburst first
					8 send toneburst at end */
				if (changed_burst) // toneburst first and toneburst changed
				{
					if (di_param.m_command_order&1)
					{
						send_mask |= 4;
						if ( send_csw )
							send_mask |= 1;
						if ( send_ucsw )
							send_mask |= 2;
					}
					else
						send_mask |= 8;
				}
				if (changed_ucsw)
				{
					send_mask |= 2;
					if ((di_param.m_command_order&4) && send_csw)
						send_mask |= 1;
					if (di_param.m_command_order==4 && send_burst)
						send_mask |= 8;
				}
				if (changed_csw)
				{
					if ( di_param.m_use_fast
						&& di_param.m_committed_cmd < eDVBSatelliteDiseqcParameters::SENDNO
						&& (lastcsw & 0xF0)
						&& ((csw / 4) == (lastcsw / 4)) )
						eDebugNoSimulate("dont send committed cmd (fast diseqc)");
					else
					{
						send_mask |= 1;
						if (!(di_param.m_command_order&4) && send_ucsw)
							send_mask |= 2;
						if (!(di_param.m_command_order&1) && send_burst)
							send_mask |= 8;
					}
				}

#if 0
				eDebugNoNewLine("sendmask: ");
				for (int i=3; i >= 0; --i)
					if ( send_mask & (1<<i) )
						eDebugNoNewLine("1");
					else
						eDebugNoNewLine("0");
				eDebug("%s", "");
#endif
				if ( diseqc_mode == eDVBSatelliteDiseqcParameters::V1_2
					&& !sat.no_rotor_command_on_tune )
				{
					if (sw_param.m_rotorPosNum) // we have stored rotor pos?
						RotorCmd=sw_param.m_rotorPosNum;
					else  // we must calc gotoxx cmd
					{
						eDebugNoSimulate("Entry for %d,%d? not in Rotor Table found... i try gotoXX?", sat.orbital_position / 10, sat.orbital_position % 10 );
						useGotoXX = true;

						double	SatLon = abs(sat.orbital_position)/10.00,
								SiteLat = rotor_param.m_gotoxx_parameters.m_latitude,
								SiteLon = rotor_param.m_gotoxx_parameters.m_longitude;

						if ( rotor_param.m_gotoxx_parameters.m_la_direction == eDVBSatelliteRotorParameters::SOUTH )
							SiteLat = -SiteLat;

						if ( rotor_param.m_gotoxx_parameters.m_lo_direction == eDVBSatelliteRotorParameters::WEST )
							SiteLon = 360 - SiteLon;

						eDebugNoSimulate("siteLatitude = %lf, siteLongitude = %lf, %lf degrees", SiteLat, SiteLon, SatLon );
						double satHourAngle =
							calcSatHourangle( SatLon, SiteLat, SiteLon );
						eDebugNoSimulate("PolarmountHourAngle=%lf", satHourAngle );

						static int gotoXTable[10] =
							{ 0x00, 0x02, 0x03, 0x05, 0x06, 0x08, 0x0A, 0x0B, 0x0D, 0x0E };

						if (SiteLat >= 0) // Northern Hemisphere
						{
							int tmp=(int)round( fabs( 180 - satHourAngle ) * 10.0 );
							RotorCmd = (tmp/10)*0x10 + gotoXTable[ tmp % 10 ];

							if (satHourAngle < 180) // the east
								RotorCmd |= 0xE000;
							else					// west
								RotorCmd |= 0xD000;
						}
						else // Southern Hemisphere
						{
							if (satHourAngle < 180) // the east
							{
								int tmp=(int)round( fabs( satHourAngle ) * 10.0 );
								RotorCmd = (tmp/10)*0x10 + gotoXTable[ tmp % 10 ];
								RotorCmd |= 0xD000;
							}
							else // west
							{
								int tmp=(int)round( fabs( 360 - satHourAngle ) * 10.0 );
								RotorCmd = (tmp/10)*0x10 + gotoXTable[ tmp % 10 ];
								RotorCmd |= 0xE000;
							}
						}
						eDebugNoSimulate("RotorCmd = %04x", RotorCmd);
					}
				}

				if ( send_mask )
				{
					int diseqc_repeats = diseqc_mode > eDVBSatelliteDiseqcParameters::V1_0 ? di_param.m_repeats : 0;
					int vlt = iDVBFrontend::voltageOff;
					eSecCommand::pair compare;
					compare.steps = +3;
					compare.tone = iDVBFrontend::toneOff;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_TONE_GOTO, compare) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_TONE, iDVBFrontend::toneOff) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_CONT_TONE_DISABLE_BEFORE_DISEQC]) );

					if (diseqc13V)
						vlt = iDVBFrontend::voltage13;
					else if ( RotorCmd != -1 && RotorCmd != lastRotorCmd )
					{
						if (rotor_param.m_inputpower_parameters.m_use && !is_unicable)
							vlt = VOLTAGE(18);  // in input power mode set 18V for measure input power
						else
							vlt = VOLTAGE(13);  // in normal mode start turning with 13V
					}
					else
						vlt = voltage;

					// check if voltage is already correct..
					compare.voltage = vlt;
					compare.steps = +7;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare) );

					// check if voltage is disabled
					compare.voltage = iDVBFrontend::voltageOff;
					compare.steps = +4;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare) );

					// voltage is changed... use DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_SWITCH_CMDS
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, vlt) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_SWITCH_CMDS]) );
					sec_sequence.push_back( eSecCommand(eSecCommand::GOTO, +3) );

					// voltage was disabled.. use DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_SWITCH_CMDS
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, vlt) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_SWITCH_CMDS]) );

					sec_sequence.push_back( eSecCommand(eSecCommand::INVALIDATE_CURRENT_SWITCHPARMS) );
					if (needDiSEqCReset)
					{
						eDVBDiseqcCommand diseqc;
						memset(diseqc.data, 0, MAX_DISEQC_LENGTH);
						diseqc.len = 3;
						diseqc.data[0] = 0xE0;
						diseqc.data[1] = 0;
						diseqc.data[2] = 0;
						// diseqc reset
						sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
						sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_DISEQC_RESET_CMD]) );
						diseqc.data[2] = 3;
						// diseqc peripherial powersupply on
						sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
						sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_DISEQC_PERIPHERIAL_POWERON_CMD]) );
					}

					for (int seq_repeat = 0; seq_repeat < (di_param.m_seq_repeat?2:1); ++seq_repeat)
					{
						if ( send_mask & 4 )
						{
							sec_sequence.push_back( eSecCommand(eSecCommand::SEND_TONEBURST, di_param.m_toneburst_param) );
							sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_TONEBURST]) );
						}

						int loops=0;

						if ( send_mask & 1 )
							++loops;
						if ( send_mask & 2 )
							++loops;

						loops <<= diseqc_repeats;

						for ( int i = 0; i < loops;)  // fill commands...
						{
							eDVBDiseqcCommand diseqc;
							memset(diseqc.data, 0, MAX_DISEQC_LENGTH);
							diseqc.len = 4;
							diseqc.data[0] = i ? 0xE1 : 0xE0;
							diseqc.data[1] = 0x10;
							if ( (send_mask & 2) && (di_param.m_command_order & 4) )
							{
								diseqc.data[2] = 0x39;
								diseqc.data[3] = ucsw;
							}
							else if ( send_mask & 1 )
							{
								diseqc.data[2] = 0x38;
								diseqc.data[3] = csw;
							}
							else  // no committed command confed.. so send uncommitted..
							{
								diseqc.data[2] = 0x39;
								diseqc.data[3] = ucsw;
							}
							sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );

							i++;
							if ( i < loops )
							{
								int cmd=0;
								if (diseqc.data[2] == 0x38 && (send_mask & 2))
									cmd=0x39;
								else if (diseqc.data[2] == 0x39 && (send_mask & 1))
									cmd=0x38;
								int tmp = m_params[DELAY_BETWEEN_DISEQC_REPEATS];
								if (cmd)
								{
									int delay = diseqc_repeats ? (tmp - 54) / 2 : tmp;  // standard says 100msek between two repeated commands
									sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, delay) );
									diseqc.data[2]=cmd;
									diseqc.data[3]=(cmd==0x38) ? csw : ucsw;
									sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
									++i;
									if ( i < loops )
										sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, delay ) );
									else
										sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_LAST_DISEQC_CMD]) );
								}
								else  // delay 120msek when no command is in repeat gap
									sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, tmp) );
							}
							else
								sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_LAST_DISEQC_CMD]) );
						}

						if ( send_mask & 8 )  // toneburst at end of sequence
						{
							sec_sequence.push_back( eSecCommand(eSecCommand::SEND_TONEBURST, di_param.m_toneburst_param) );
							sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_TONEBURST]) );
						}

						if (di_param.m_seq_repeat && seq_repeat == 0)
							sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_BEFORE_SEQUENCE_REPEAT]) );
					}
				}
			}
			else
			{
				sec_sequence.push_back( eSecCommand(eSecCommand::INVALIDATE_CURRENT_SWITCHPARMS) );
				csw = band;
			}

			sec_fe->setData(eDVBFrontend::NEW_CSW, csw);
			sec_fe->setData(eDVBFrontend::NEW_UCSW, ucsw);
			sec_fe->setData(eDVBFrontend::NEW_TONEBURST, di_param.m_toneburst_param);

			if(is_unicable)
			{
				// check if voltage is disabled
				eSecCommand::pair compare;
				compare.steps = +3;
				compare.voltage = iDVBFrontend::voltageOff;
				sec_sequence.push_back( eSecCommand(eSecCommand::IF_NOT_VOLTAGE_GOTO, compare) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(13)) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_SWITCH_CMDS] ) );

				sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(18)) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_TONE, iDVBFrontend::toneOff) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_SWITCH_CMDS]) );  // wait 20 ms after voltage change
	
				eDVBDiseqcCommand diseqc;
				memset(diseqc.data, 0, MAX_DISEQC_LENGTH);
				diseqc.len = 5;
				diseqc.data[0] = 0xE0;
				diseqc.data[1] = 0x10;
				diseqc.data[2] = 0x5A;
				diseqc.data[3] = lnb_param.UnicableTuningWord >> 8;
				diseqc.data[4] = lnb_param.UnicableTuningWord;

				sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_LAST_DISEQC_CMD]) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(13)) );
				if ( RotorCmd != -1 && RotorCmd != lastRotorCmd && !rotor_param.m_inputpower_parameters.m_use)
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MOTOR_CMD]) );  // wait 150msec after voltage change
			}

			eDebugNoSimulate("RotorCmd %02x, lastRotorCmd %02lx", RotorCmd, lastRotorCmd);
			/* HDSatelit (urma motorului): hotararea pentru motor intra in acordarea tunerului (comenzile secventei o poarta
			   cu ele), iar o acordare pe satelitul pe care nucleul crede ca e deja antena se noteaza: atunci nu pleaca
			   nimic spre motor, oricat ar fi de departe antena in realitate (la reacordare mereu, altfel rar) */
			if (!simulate)
			{
				hdsurma::Acordare &hds_a = ((eDVBFrontend*)&frontend)->hdsAcordare();
				hds_a.rotor_de_la = (int)curRotorPos;
				hds_a.rotor_cmd = RotorCmd;
				hds_a.rotor_cmd_vechi = (int)lastRotorCmd;
				if (RotorCmd != -1 && RotorCmd == lastRotorCmd)
					hdsurma::gotoOmis(((eDVBFrontend*)&frontend)->getSlotID(), hds_a, lastRotorCmd);
			}
			if ( RotorCmd != -1 && RotorCmd != lastRotorCmd )
			{
				int mrt = m_params[MOTOR_RUNNING_TIMEOUT]; // in seconds!
				/* HDSatelit (lib/dvb/hdsrotire.h): pe ramura fara masurarea curentului (si fara Unicable)
				   motorul se roteste pe 18 V cand mutarea nu e de 0 grade; aici: de unde pleaca antena, cat are de mers si,
				   spre o tinta pe 13 V, cat se tine 18 V (plafonat mai jos cu mrt). Ramura cu masurare nu foloseste nimic. */
				hdsrotire::Plan hds_plan;
				int hds_proba = hdsrotire::PROBA_NECERUTA;
				int hds_slot = ((eDVBFrontend*)&frontend)->getSlotID();
				if (!rotor_param.m_inputpower_parameters.m_use && !is_unicable)
				{
					int hds_radacina = ((eDVBFrontend*)sec_fe)->getSlotID();
					bool hds_zona_ok = hds_radacina >= 0 && hds_radacina < HDS_MAX_ROTOR_SLOTS;
					hdsrotire::Zona hds_fara_zona;
					hdsrotire::Loc hds_loc = hdsrotire::loc(rotor_param.m_gotoxx_parameters.m_latitude,
						rotor_param.m_gotoxx_parameters.m_la_direction == eDVBSatelliteRotorParameters::SOUTH,
						rotor_param.m_gotoxx_parameters.m_longitude,
						rotor_param.m_gotoxx_parameters.m_lo_direction == eDVBSatelliteRotorParameters::WEST);
					hds_plan = hdsrotire::planifica((int)curRotorPos, sat.orbital_position, voltage == VOLTAGE(18) ? 1 : 0,
						hds_loc, hdsModelMotor(hds_slot, hds_radacina), hds_zona_ok ? s_hds_zona[hds_radacina] : hds_fara_zona);
					if (!simulate && hds_zona_ok)
						s_hds_zona[hds_radacina] = hdsrotire::zonaDupa((int)curRotorPos, sat.orbital_position, hds_loc,
							s_hds_zona[hds_radacina]);
					/* plecarea necunoscuta spre o tinta pe 13 V: intai semnalul tintei cu antena pe loc, numai daca
					   transponderul nu are geaman pe alt satelit al motorului (lib/dvb/hdsrotire.h) */
					if (hdsrotire::probaPosibila(hds_plan))
					{
						int hds_geaman = hdsrotire::areGeaman(hdsTranspondereMotor(hds_slot, hds_radacina), sat.orbital_position,
							sat.polarisation, (int)sat.frequency, (int)sat.symbol_rate);
						hds_proba = hds_geaman == 0 ? hdsrotire::PROBA_FACUTA
							: (hds_geaman > 0 ? hdsrotire::PROBA_GEAMAN : hdsrotire::PROBA_FARA_LISTA);
					}
				}
				eSecCommand::pair compare;
				if (!send_mask && !is_unicable)
				{
					compare.steps = +3;
					compare.tone = iDVBFrontend::toneOff;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_TONE_GOTO, compare) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_TONE, iDVBFrontend::toneOff) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_CONT_TONE_DISABLE_BEFORE_DISEQC]) );

					compare.voltage = iDVBFrontend::voltageOff;
					compare.steps = +4;
					// the next is a check if voltage is switched off.. then we first set a voltage :)
					// else we set voltage after all diseqc stuff..
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_NOT_VOLTAGE_GOTO, compare) );

					if (rotor_param.m_inputpower_parameters.m_use)
						sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(18)) ); // set 18V for measure input power
					else if (hds_plan.pe18 && !diseqc13V)
						sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(18)) ); // HDSatelit (motor-18v): motorul pe 18 V
					else
						sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(13)) ); // in normal mode start turning with 13V

					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_MOTOR_CMD]) ); // wait 750ms when voltage was disabled
					sec_sequence.push_back( eSecCommand(eSecCommand::GOTO, +9) );  // no need to send stop rotor cmd and recheck voltage
				}
				else
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_BETWEEN_SWITCH_AND_MOTOR_CMD]) ); // wait 700ms when diseqc changed

				eDVBDiseqcCommand diseqc;
				memset(diseqc.data, 0, MAX_DISEQC_LENGTH);
				diseqc.len = 3;
				diseqc.data[0] = 0xE0;
				diseqc.data[1] = 0x31;	// positioner
				diseqc.data[2] = 0x60;	// stop
				sec_sequence.push_back( eSecCommand(eSecCommand::IF_ROTORPOS_VALID_GOTO, +5) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, 50) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
				// wait 150msec after send rotor stop cmd
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_MOTOR_STOP_CMD]) );

				diseqc.data[0] = 0xE0;
				diseqc.data[1] = 0x31;		// positioner
				if ( useGotoXX )
				{
					diseqc.len = 5;
					diseqc.data[2] = 0x6E;	// drive to angular position
					diseqc.data[3] = ((RotorCmd & 0xFF00) / 0x100);
					diseqc.data[4] = RotorCmd & 0xFF;
				}
				else
				{
					diseqc.len = 4;
					diseqc.data[2] = 0x6B;	// goto stored sat position
					diseqc.data[3] = RotorCmd;
					diseqc.data[4] = 0x00;
				}

			// use measure rotor input power to detect motor state
				if ( rotor_param.m_inputpower_parameters.m_use)
				{
					bool turn_fast = need_turn_fast(rotor_param.m_inputpower_parameters.m_turning_speed) && !is_unicable;
					eSecCommand::rotor cmd;
					eSecCommand::pair compare;
					if (turn_fast)
						compare.voltage = VOLTAGE(18);
					else
						compare.voltage = VOLTAGE(13);
					compare.steps = +3;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, compare.voltage) );
			// measure idle power values
					compare.steps = -2;
					if (turn_fast) {
						sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MEASURE_IDLE_INPUTPOWER]) );  // wait 150msec after voltage change
						sec_sequence.push_back( eSecCommand(eSecCommand::MEASURE_IDLE_INPUTPOWER, 1) );
						compare.val = 1;
						sec_sequence.push_back( eSecCommand(eSecCommand::IF_MEASURE_IDLE_WAS_NOT_OK_GOTO, compare) );
						sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(13)) );
					}
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MEASURE_IDLE_INPUTPOWER]) );  // wait 150msec before measure
					sec_sequence.push_back( eSecCommand(eSecCommand::MEASURE_IDLE_INPUTPOWER, 0) );
					compare.val = 0;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_MEASURE_IDLE_WAS_NOT_OK_GOTO, compare) );
			////////////////////////////
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_ROTOR_DISEQC_RETRYS, m_params[MOTOR_COMMAND_RETRIES]) );  // 2 retries
					sec_sequence.push_back( eSecCommand(eSecCommand::INVALIDATE_CURRENT_ROTORPARMS) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_TIMEOUT, 40) );  // 2 seconds rotor start timout
			// rotor start loop
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, 50) );  // 50msec delay
					sec_sequence.push_back( eSecCommand(eSecCommand::MEASURE_RUNNING_INPUTPOWER) );
					cmd.direction=1;  // check for running rotor
					cmd.deltaA=rotor_param.m_inputpower_parameters.m_delta;
					cmd.steps=+5;
					cmd.okcount=0;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_INPUTPOWER_DELTA_GOTO, cmd ) );  // check if rotor has started
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_TIMEOUT_GOTO, +2 ) );  // timeout .. we assume now the rotor is already at the correct position
					sec_sequence.push_back( eSecCommand(eSecCommand::GOTO, -4) );  // goto loop start
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_NO_MORE_ROTOR_DISEQC_RETRYS_GOTO, turn_fast ? 10 : 9 ) );  // timeout .. we assume now the rotor is already at the correct position	
					sec_sequence.push_back( eSecCommand(eSecCommand::GOTO, -8) );  // goto loop start
			////////////////////
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_ROTOR_MOVING) );
					if (turn_fast)
						sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, VOLTAGE(18)) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_TIMEOUT, mrt*20) );  // mrt is in seconds... our SLEEP time is 50ms.. so * 20
			// rotor running loop
					sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, 50) );  // wait 50msec
					sec_sequence.push_back( eSecCommand(eSecCommand::MEASURE_RUNNING_INPUTPOWER) );
					cmd.direction=0;  // check for stopped rotor
					cmd.steps=+3;
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_INPUTPOWER_DELTA_GOTO, cmd ) );
					sec_sequence.push_back( eSecCommand(eSecCommand::IF_TIMEOUT_GOTO, +2 ) );  // timeout ? this should never happen
					sec_sequence.push_back( eSecCommand(eSecCommand::GOTO, -4) );  // running loop start
			/////////////////////
					sec_sequence.push_back( eSecCommand(eSecCommand::UPDATE_CURRENT_ROTORPARAMS) );
					sec_sequence.push_back( eSecCommand(eSecCommand::SET_ROTOR_STOPPED) );
				}
			// use normal motor turning mode
				else
				{
					if (curRotorPos != -1)
					{
						mrt = abs(curRotorPos - sat.orbital_position);
						if (mrt > 1800)
							mrt = 3600 - mrt;
						if (mrt % 10)
							mrt += 10; // round a little bit
						mrt *= 2000;  // (we assume a very slow rotor with just 0.5 degree per second here)
						mrt /= 10000;
						mrt += 3; // a little bit overhead
					}
					doSetVoltageToneFrontend=false;
					doSetFrontend=false;
					/* HDSatelit (lib/dvb/hdsrotire.h): aceeasi secventa, cu motorul pe 18 V cand mutarea nu e
					   de 0 grade; spre o tinta pe 13 V, 18 V se tine cat dureaza mutarea estimata, apoi tensiunea si tonul tintei
					   si bucla de semnal. Fara 18 V (0 grade) secventa e exact cea de dinainte. */
					hdsrotire::plafoneaza(hds_plan, mrt);
					hdsrotire::Secventa hds_s;
					hds_s.comanda = &diseqc;
					hds_s.v13 = VOLTAGE(13);
					hds_s.v18 = VOLTAGE(18);
					hds_s.tensiune = voltage;
					hds_s.ton = tone;
					hds_s.diseqc13v = diseqc13V ? 1 : 0;
					hds_s.dupa_tensiune_ms = m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MOTOR_CMD];
					hds_s.dupa_diseqc_ms = m_params[DELAY_AFTER_LAST_DISEQC_CMD];
					hds_s.dupa_ton_ms = m_params[DELAY_AFTER_FINAL_CONT_TONE_CHANGE];
					hds_s.mrt_s = mrt;
					hds_s.tunetimeout = tunetimeout;
					hds_s.proba = hds_proba == hdsrotire::PROBA_FACUTA ? 1 : 0;
					hds_s.dupa_ton_oprit_ms = m_params[DELAY_AFTER_CONT_TONE_DISABLE_BEFORE_DISEQC];
					int hds_total_s = hdsrotire::secventaFaraMasurare(sec_sequence, hds_s, hds_plan);
					eDebug("set rotor timeout to %d seconds", mrt);
					if (hds_plan.pe18)
						eDebugNoSimulate("[SEC] hds motor pe 18 V: %.1f grade (plecare %d), tinta pe %d V, 18 V tinut %d ms, timpul maxim %d s, proba %d",
							hds_plan.grade, hds_plan.plecare, hds_plan.tinta18 ? 18 : 13, hds_plan.tinere_ms, hds_total_s, hds_proba);
					if (!simulate)
					{
						/* urma motorului: tensiunea de rotire intra in randul comenzii de motor */
						hdsurma::Acordare &hds_r = ((eDVBFrontend*)&frontend)->hdsAcordare();
						hds_r.rotire_tensiune = hds_plan.pe18 ? 18 : 13;
						hds_r.rotire_tinta = voltage == VOLTAGE(18) ? 18 : 13;
						hds_r.rotire_plan_ms = (hds_plan.pe18 && !hds_plan.tinta18) ? hds_plan.tinere_ms : 0;
						hds_r.rotire_grade_zecimi = (int)(hds_plan.grade * 10.0 + 0.5);
						hds_r.rotire_plecare = hds_plan.plecare;
						hds_r.rotire_proba = hds_proba;
					}
					mrt = hds_total_s;
				}
				sec_fe->setData(eDVBFrontend::NEW_ROTOR_CMD, RotorCmd);
				sec_fe->setData(eDVBFrontend::NEW_ROTOR_POS, sat.orbital_position);
				/* HDSatelit: aici stim tot ce ii trebuie ecranului de rotire: de unde plecam
				   (curRotorPos, ultima pozitie confirmata, -1 daca nu s-a confirmat niciuna de la pornire),
				   unde mergem, ce comanda am pus pe fir si cat da sec.cpp ca timp maxim. Nu se noteaza
				   nimic pentru frontendurile simulate, ca o simpla verificare de alocare sa nu stearga
				   informatia despre o miscare adevarata aflata in curs. */
				if (!simulate)
					hdsNoteRotorMovement(((eDVBFrontend*)&frontend)->getSlotID(), curRotorPos, sat.orbital_position, RotorCmd, useGotoXX ? 1 : 0, mrt);
				/* HDSatelit: cat se tine 18 V dupa comanda, pentru urma si pentru Components/HdsMotorViteza.py
				   (o sosire tinuta de 18 V nu spune viteza motorului) */
				if (!simulate && hds_slot >= 0 && hds_slot < HDS_MAX_ROTOR_SLOTS)
					m_hds_rotor[hds_slot].tinere_ms = (hds_plan.pe18 && !hds_plan.tinta18) ? hds_plan.tinere_ms : 0;
			}

			if (doSetVoltageToneFrontend && !is_unicable)
			{
				eSecCommand::pair compare;
				compare.voltage = voltage;
				compare.steps = +3;
				sec_sequence.push_back( eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare) ); // voltage already correct ?
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, voltage) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_FINAL_VOLTAGE_CHANGE]) );
				compare.tone = tone;
				sec_sequence.push_back( eSecCommand(eSecCommand::IF_TONE_GOTO, compare) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_TONE, tone) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_FINAL_CONT_TONE_CHANGE]) );
			}

			sec_sequence.push_back( eSecCommand(eSecCommand::UPDATE_CURRENT_SWITCHPARMS) );

			if (doSetFrontend)
			{
				sec_sequence.push_back( eSecCommand(eSecCommand::START_TUNE_TIMEOUT, tunetimeout) );
				sec_sequence.push_back( eSecCommand(eSecCommand::SET_FRONTEND, 1) );
			}

			sec_sequence.push_front( eSecCommand(eSecCommand::SET_POWER_LIMITING_MODE, eSecCommand::modeStatic) );
			sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, 500) );
			sec_sequence.push_back( eSecCommand(eSecCommand::SET_POWER_LIMITING_MODE, eSecCommand::modeDynamic) );

			frontend.setSecSequence(sec_sequence);

			return 0;
		}
	}
	eDebugNoSimulate("found no useable satellite configuration for %s freq %d%s %s on orbital position (%d)",
		sat.system ? "DVB-S2" : "DVB-S",
		sat.frequency,
		sat.polarisation == eDVBFrontendParametersSatellite::Polarisation_Horizontal ? "H" :
			sat.polarisation == eDVBFrontendParametersSatellite::Polarisation_Vertical ? "V" :
			sat.polarisation == eDVBFrontendParametersSatellite::Polarisation_CircularLeft ? "CL" : "CR",
		sat.modulation == eDVBFrontendParametersSatellite::Modulation_Auto ? "AUTO" :
			sat.modulation == eDVBFrontendParametersSatellite::Modulation_QPSK ? "QPSK" :
			sat.modulation == eDVBFrontendParametersSatellite::Modulation_8PSK ? "8PSK" : "QAM16",
		sat.orbital_position );
	return -1;
}

void eDVBSatelliteEquipmentControl::prepareTurnOffSatCR(iDVBFrontend &frontend, int satcr)
{
	eSecCommandList sec_sequence;

	// check if voltage is disabled
	eSecCommand::pair compare;
	compare.steps = +9;	//only close frontend
	compare.voltage = iDVBFrontend::voltageOff;

	sec_sequence.push_back( eSecCommand(eSecCommand::IF_VOLTAGE_GOTO, compare) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, iDVBFrontend::voltage13) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_SWITCH_CMDS]) );

	sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, iDVBFrontend::voltage18_5) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SET_TONE, iDVBFrontend::toneOff) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_SWITCH_CMDS]) );

	eDVBDiseqcCommand diseqc;
	memset(diseqc.data, 0, MAX_DISEQC_LENGTH);
	diseqc.len = 5;
	diseqc.data[0] = 0xE0;
	diseqc.data[1] = 0x10;
	diseqc.data[2] = 0x5A;
	diseqc.data[3] = satcr << 5;
	diseqc.data[4] = 0x00;

	sec_sequence.push_back( eSecCommand(eSecCommand::SEND_DISEQC, diseqc) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SLEEP, m_params[DELAY_AFTER_LAST_DISEQC_CMD]) );
	sec_sequence.push_back( eSecCommand(eSecCommand::SET_VOLTAGE, iDVBFrontend::voltage13) );
	sec_sequence.push_back( eSecCommand(eSecCommand::DELAYED_CLOSE_FRONTEND) );

	frontend.setSecSequence(sec_sequence);
}

RESULT eDVBSatelliteEquipmentControl::clear()
{
	eSecDebug("eDVBSatelliteEquipmentControl::clear()");
	for (int i=0; i <= m_lnbidx; ++i)
	{
		m_lnbs[i].m_satellites.clear();
		m_lnbs[i].m_slot_mask = 0;
		m_lnbs[i].m_prio = -1; // auto
	}
	m_lnbidx=-1;

	m_not_linked_slot_mask=0;

	/* HDSatelit: pozitiile se uita mai jos, iar locul antenei se poate schimba: nicio zona */
	for (int i = 0; i < HDS_MAX_ROTOR_SLOTS; ++i)
		s_hds_zona[i] = hdsrotire::Zona();

	//reset some tuner configuration
	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_frontends.begin()); it != m_avail_frontends.end(); ++it)
	{
		it->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::LINKED_PREV_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::LINKED_NEXT_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::ROTOR_POS, -1);
		it->m_frontend->setData(eDVBFrontend::ROTOR_CMD, -1);
		it->m_frontend->setData(eDVBFrontend::SATCR, -1);
	}

	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_simulate_frontends.begin()); it != m_avail_simulate_frontends.end(); ++it)
	{
		it->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::LINKED_PREV_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::LINKED_NEXT_PTR, -1);
		it->m_frontend->setData(eDVBFrontend::ROTOR_POS, -1);
		it->m_frontend->setData(eDVBFrontend::ROTOR_CMD, -1);
		it->m_frontend->setData(eDVBFrontend::SATCR, -1);
	}

	return 0;
}

/* LNB Specific Parameters */
RESULT eDVBSatelliteEquipmentControl::addLNB()
{
	if ( (m_lnbidx+1) < (int)(sizeof(m_lnbs) / sizeof(eDVBSatelliteLNBParameters)))
		m_curSat=m_lnbs[++m_lnbidx].m_satellites.end();
	else
	{
		eDebug("no more LNB free... cnt is %d", m_lnbidx);
		return -ENOSPC;
	}
	eSecDebug("eDVBSatelliteEquipmentControl::addLNB(%d)", m_lnbidx);
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBSlotMask(int slotmask)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBSlotMask(%d)", slotmask);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_slot_mask = slotmask;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBLOFL(int lofl)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBLOFL(%d)", lofl);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_lof_lo = lofl;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBLOFH(int lofh)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBLOFH(%d)", lofh);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_lof_hi = lofh;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBThreshold(int threshold)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBThreshold(%d)", threshold);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_lof_threshold = threshold;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBIncreasedVoltage(bool onoff)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBIncreasedVoltage(%d)", onoff);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_increased_voltage = onoff;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBPrio(int prio)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBPrio(%d)", prio);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_prio = prio;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBNum(int LNBNum)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBNum(%d)", LNBNum);
	if(!((LNBNum >= 1) && (LNBNum <= MAX_LNBNUM)))
		return -EPERM;
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].LNBNum = LNBNum;
	else
		return -ENOENT;
	return 0;
}

/* DiSEqC Specific Parameters */
RESULT eDVBSatelliteEquipmentControl::setDiSEqCMode(int diseqcmode)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setDiSEqcMode(%d)", diseqcmode);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_diseqc_mode = (eDVBSatelliteDiseqcParameters::t_diseqc_mode)diseqcmode;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setToneburst(int toneburst)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setToneburst(%d)", toneburst);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_toneburst_param = (eDVBSatelliteDiseqcParameters::t_toneburst_param)toneburst;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setRepeats(int repeats)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setRepeats(%d)", repeats);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_repeats=repeats;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setCommittedCommand(int command)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setCommittedCommand(%d)", command);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_committed_cmd=command;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setUncommittedCommand(int command)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setUncommittedCommand(%d)", command);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_uncommitted_cmd = command;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setCommandOrder(int order)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setCommandOrder(%d)", order);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_command_order=order;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setFastDiSEqC(bool onoff)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setFastDiSEqc(%d)", onoff);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_use_fast=onoff;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setSeqRepeat(bool onoff)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setSeqRepeat(%d)", onoff);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_diseqc_parameters.m_seq_repeat = onoff;
	else
		return -ENOENT;
	return 0;
}

/* Rotor Specific Parameters */
RESULT eDVBSatelliteEquipmentControl::setLongitude(float longitude)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLongitude(%f)", longitude);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_gotoxx_parameters.m_longitude=longitude;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLatitude(float latitude)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLatitude(%f)", latitude);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_gotoxx_parameters.m_latitude=latitude;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLoDirection(int direction)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLoDirection(%d)", direction);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_gotoxx_parameters.m_lo_direction=direction;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLaDirection(int direction)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLaDirection(%d)", direction);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_gotoxx_parameters.m_la_direction=direction;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setUseInputpower(bool onoff)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setUseInputpower(%d)", onoff);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_inputpower_parameters.m_use=onoff;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setInputpowerDelta(int delta)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setInputpowerDelta(%d)", delta);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_inputpower_parameters.m_delta=delta;
	else
		return -ENOENT;
	return 0;
}

/* Unicable Specific Parameters */
RESULT eDVBSatelliteEquipmentControl::setLNBSatCR(int SatCR_idx)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBSatCR(%d)", SatCR_idx);
	if(!((SatCR_idx >=-1) && (SatCR_idx < MAX_SATCR)))
		return -EPERM;
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].SatCR_idx = SatCR_idx;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBSatCRvco(int SatCRvco)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBSatCRvco(%d)", SatCRvco);
	if(!((SatCRvco >= 950*1000) && (SatCRvco <= 2150*1000)))
		return -EPERM;
	if(!((m_lnbs[m_lnbidx].SatCR_idx >= 0) && (m_lnbs[m_lnbidx].SatCR_idx < MAX_SATCR)))
		return -ENOENT;
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].SatCRvco = SatCRvco;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setLNBSatCRpositions(int SatCR_positions)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setLNBSatCRpositions(%d)", SatCR_positions);
	if(SatCR_positions < 1 || SatCR_positions > 2)
		return -EPERM;
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].SatCR_positions = SatCR_positions;
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::getLNBSatCRpositions()
{
	if ( currentLNBValid() )
		return m_lnbs[m_lnbidx].SatCR_positions;
	return -ENOENT;
}

RESULT eDVBSatelliteEquipmentControl::getLNBSatCR()
{
	if ( currentLNBValid() )
		return m_lnbs[m_lnbidx].SatCR_idx;
	return -ENOENT;
}

RESULT eDVBSatelliteEquipmentControl::getLNBSatCRvco()
{
	if ( currentLNBValid() )
		return m_lnbs[m_lnbidx].SatCRvco;
	return -ENOENT;
}

/* Satellite Specific Parameters */
RESULT eDVBSatelliteEquipmentControl::addSatellite(int orbital_position)
{
	eSecDebug("eDVBSatelliteEquipmentControl::addSatellite(%d)", orbital_position);
	if ( currentLNBValid() )
	{
		std::map<int, eDVBSatelliteSwitchParameters>::iterator it =
			m_lnbs[m_lnbidx].m_satellites.find(orbital_position);
		if ( it == m_lnbs[m_lnbidx].m_satellites.end() )
		{
			std::pair<std::map<int, eDVBSatelliteSwitchParameters>::iterator, bool > ret =
				m_lnbs[m_lnbidx].m_satellites.insert(
					std::pair<int, eDVBSatelliteSwitchParameters>(orbital_position, eDVBSatelliteSwitchParameters())
				);
			if ( ret.second )
				m_curSat = ret.first;
			else
				return -ENOMEM;
		}
		else
			return -EEXIST;
	}
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setVoltageMode(int mode)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setVoltageMode(%d)", mode);
	if ( currentLNBValid() && m_curSat != m_lnbs[m_lnbidx].m_satellites.end() )
		m_curSat->second.m_voltage_mode = (eDVBSatelliteSwitchParameters::t_voltage_mode)mode;
	else
		return -ENOENT;
	return 0;

}

RESULT eDVBSatelliteEquipmentControl::setToneMode(int mode)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setToneMode(%d)", mode);
	if ( currentLNBValid() )
	{
		if ( m_curSat != m_lnbs[m_lnbidx].m_satellites.end() )
			m_curSat->second.m_22khz_signal = (eDVBSatelliteSwitchParameters::t_22khz_signal)mode;
		else
			return -EPERM;
	}
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setRotorPosNum(int rotor_pos_num)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setRotorPosNum(%d)", rotor_pos_num);
	if ( currentLNBValid() )
	{
		if ( m_curSat != m_lnbs[m_lnbidx].m_satellites.end() )
			m_curSat->second.m_rotorPosNum=rotor_pos_num;
		else
			return -EPERM;
	}
	else
		return -ENOENT;
	return 0;
}

RESULT eDVBSatelliteEquipmentControl::setRotorTurningSpeed(int speed)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setRotorTurningSpeed(%d)", speed);
	if ( currentLNBValid() )
		m_lnbs[m_lnbidx].m_rotor_parameters.m_inputpower_parameters.m_turning_speed = speed;
	else
		return -ENOENT;
	return 0;
}

struct sat_compare
{
	int orb_pos, lofl, lofh;
	sat_compare(int o, int lofl, int lofh)
		:orb_pos(o), lofl(lofl), lofh(lofh)
	{}
	sat_compare(const sat_compare &x)
		:orb_pos(x.orb_pos), lofl(x.lofl), lofh(x.lofh)
	{}
	bool operator < (const sat_compare & cmp) const
	{
		if (orb_pos == cmp.orb_pos)
		{
			if ( abs(lofl-cmp.lofl) < 200000 )
			{
				if (abs(lofh-cmp.lofh) < 200000)
					return false;
				return lofh<cmp.lofh;
			}
			return lofl<cmp.lofl;
		}
		return orb_pos < cmp.orb_pos;
	}
};

RESULT eDVBSatelliteEquipmentControl::setTunerLinked(int tu1, int tu2)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setTunerLinked(%d, %d)", tu1, tu2);
	if (tu1 != tu2)
	{
		eDVBRegisteredFrontend *p1=NULL, *p2=NULL;
		eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_frontends.begin());
		for (; it != m_avail_frontends.end(); ++it)
		{
			if (it->m_frontend->getSlotID() == tu1)
				p1 = *it;
			else if (it->m_frontend->getSlotID() == tu2)
				p2 = *it;
		}
		if (p1 && p2)
		{
			p1->m_frontend->setData(eDVBFrontend::LINKED_PREV_PTR, (long)p2);
			p2->m_frontend->setData(eDVBFrontend::LINKED_NEXT_PTR, (long)p1);
		}

		p1=p2=NULL;
		it=m_avail_simulate_frontends.begin();
		for (; it != m_avail_simulate_frontends.end(); ++it)
		{
			if (it->m_frontend->getSlotID() == tu1)
				p1 = *it;
			else if (it->m_frontend->getSlotID() == tu2)
				p2 = *it;
		}
		if (p1 && p2)
		{
			p1->m_frontend->setData(eDVBFrontend::LINKED_PREV_PTR, (long)p2);
			p2->m_frontend->setData(eDVBFrontend::LINKED_NEXT_PTR, (long)p1);
			return 0;
		}
	}
	return -1;
}

RESULT eDVBSatelliteEquipmentControl::setTunerDepends(int tu1, int tu2)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setTunerDepends(%d, %d)", tu1, tu2);
	if (tu1 == tu2)
		return -1;

	eDVBRegisteredFrontend *p1=NULL, *p2=NULL;

	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_frontends.begin()); it != m_avail_frontends.end(); ++it)
	{
		if (it->m_frontend->getSlotID() == tu1)
			p1 = *it;
		else if (it->m_frontend->getSlotID() == tu2)
			p2 = *it;
	}
	if (p1 && p2)
	{
		p1->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, (long)p2);
		p2->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, (long)p1);
	}

	p1=p2=NULL;
	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_simulate_frontends.begin()); it != m_avail_simulate_frontends.end(); ++it)
	{
		if (it->m_frontend->getSlotID() == tu1)
			p1 = *it;
		else if (it->m_frontend->getSlotID() == tu2)
			p2 = *it;
	}
	if (p1 && p2)
	{
		p1->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, (long)p2);
		p2->m_frontend->setData(eDVBFrontend::SATPOS_DEPENDS_PTR, (long)p1);
		return 0;
	}

	return -1;
}

void eDVBSatelliteEquipmentControl::setSlotNotLinked(int slot_no)
{
	eSecDebug("eDVBSatelliteEquipmentControl::setSlotNotLinked(%d)", slot_no);
	m_not_linked_slot_mask |= (1 << slot_no);
}

bool eDVBSatelliteEquipmentControl::isRotorMoving()
{
	return m_rotorMoving;
}

void eDVBSatelliteEquipmentControl::setRotorMoving(int slot_no, bool b)
{
	if (b)
		m_rotorMoving |= (1 << slot_no);
	else
		m_rotorMoving &= ~(1 << slot_no);
	/* HDSatelit: ceasul miscarii. Pornim cand frontendul spune ca motorul chiar se invarte
	   (pe ramura cu masurare de curent asta se intampla abia dupa ce curentul confirma pornirea),
	   si oprim cand spune ca s-a terminat. Inregistrarea se pastreaza dupa oprire, ca ecranul sa poata
	   arata inca vreo doua secunde ca antena a ajuns. */
	if (slot_no >= 0 && slot_no < HDS_MAX_ROTOR_SLOTS && m_hds_rotor[slot_no].valid)
	{
		if (b)
		{
			if (!m_hds_rotor[slot_no].start_ms)
				m_hds_rotor[slot_no].start_ms = hdsNowMs();
			m_hds_rotor[slot_no].stop_ms = 0;
			m_hds_rotor[slot_no].arrived = 0;
			/* tinerea pe 18 V incepe odata cu mersul */
			if (m_hds_rotor[slot_no].tinere_ms > 0 && !m_hds_rotor[slot_no].rotire)
				m_hds_rotor[slot_no].rotire = 1;
		}
		else
		{
			/* mersul oprit in timpul tinerii pe 18 V (zap, standby, oprirea din Python) */
			if (m_hds_rotor[slot_no].rotire == 1)
			{
				m_hds_rotor[slot_no].rotire = 2;
				long hds_tinut = m_hds_rotor[slot_no].start_ms ? (long)(hdsNowMs() - m_hds_rotor[slot_no].start_ms) : -1;
				hdsurma::tensiuneRotire(slot_no, "intrerupta", m_hds_rotor[slot_no].tinere_ms, hds_tinut,
					m_hds_rotor[slot_no].to_orbital, -1, 0);
			}
			if (m_hds_rotor[slot_no].start_ms && !m_hds_rotor[slot_no].stop_ms)
				m_hds_rotor[slot_no].stop_ms = hdsNowMs();
		}
	}
}

/* --- HDSatelit: starea miscarii motorului, pentru ecranul de pe televizor si ruta web --- */

long long eDVBSatelliteEquipmentControl::hdsNowMs()
{
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (long long)now.tv_sec * 1000LL + now.tv_nsec / 1000000LL;
}

void eDVBSatelliteEquipmentControl::hdsNoteRotorMovement(int slot, int from_orbital, int to_orbital, int rotor_cmd, int uses_gotoxx, int seconds)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	hdsRotorMove &m = m_hds_rotor[slot];
	m.valid = 1;
	m.from_orbital = from_orbital;
	m.to_orbital = to_orbital;
	m.rotor_cmd = rotor_cmd;
	m.uses_gotoxx = uses_gotoxx ? 1 : 0;
	m.seconds = seconds;
	m.start_ms = 0;
	m.stop_ms = 0;
	m.arrived = 0;
	m.tinere_ms = 0;
	m.rotire = 0;
}

/* HDSatelit: chemata de frontend.cpp la SET_ROTOR_STOPPED in locul lui setRotorMoving(slot, false). Semnul
   se pune numai daca miscarea era in mers chiar acum (oprirea e a ei, nu o oprire mai veche venita pe alt drum). */
void eDVBSatelliteEquipmentControl::hdsNoteRotorArrived(int slot, int locked)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	hdsRotorMove &m = m_hds_rotor[slot];
	bool in_mers = m.valid && m.start_ms && !m.stop_ms;
	setRotorMoving(slot, false);
	if (in_mers)
		m.arrived = locked ? 2 : 1;
}

int eDVBSatelliteEquipmentControl::hdsRotorArrived(int slot)
{
	if (!hdsRotorInfoValid(slot) || !m_hds_rotor[slot].stop_ms)
		return 0;
	return m_hds_rotor[slot].arrived;
}

int eDVBSatelliteEquipmentControl::hdsRotorMovingSlot()
{
	for (int slot = 0; slot < HDS_MAX_ROTOR_SLOTS; ++slot)
		if (m_rotorMoving & (1 << slot))
			return slot;
	return -1;
}

int eDVBSatelliteEquipmentControl::hdsRotorInfoValid(int slot)
{
	return (slot >= 0 && slot < HDS_MAX_ROTOR_SLOTS && m_hds_rotor[slot].valid) ? 1 : 0;
}

int eDVBSatelliteEquipmentControl::hdsRotorFromOrbital(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].from_orbital : -1;
}

int eDVBSatelliteEquipmentControl::hdsRotorToOrbital(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].to_orbital : -1;
}

int eDVBSatelliteEquipmentControl::hdsRotorCmd(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].rotor_cmd : -1;
}

int eDVBSatelliteEquipmentControl::hdsRotorUsesGotoxx(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].uses_gotoxx : 0;
}

int eDVBSatelliteEquipmentControl::hdsRotorSeconds(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].seconds : -1;
}

int eDVBSatelliteEquipmentControl::hdsRotorElapsedMs(int slot)
{
	if (!hdsRotorInfoValid(slot) || !m_hds_rotor[slot].start_ms)
		return -1;
	long long end = m_hds_rotor[slot].stop_ms ? m_hds_rotor[slot].stop_ms : hdsNowMs();
	long long value = end - m_hds_rotor[slot].start_ms;
	return value < 0 ? 0 : (int)value;
}

int eDVBSatelliteEquipmentControl::hdsRotorStoppedMs(int slot)
{
	if (!hdsRotorInfoValid(slot) || !m_hds_rotor[slot].stop_ms)
		return -1;
	long long value = hdsNowMs() - m_hds_rotor[slot].stop_ms;
	return value < 0 ? 0 : (int)value;
}

/* --- HDSatelit: pozitia motorului tinuta de nucleu --- */

/* frontendul slotului dintr-o lista si radacina lantului lui de tunere, pe acelasi drum ca prepare() (sec.cpp:343-351):
   un tuner legat (loopthrough) trimite comenzile prin radacina, deci acolo stau ROTOR_POS si ROTOR_CMD */
static eDVBFrontend *hdsSlotFrontend(eSmartPtrList<eDVBRegisteredFrontend> &list, int slot, int not_linked_mask, eDVBFrontend **root)
{
	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(list.begin()); it != list.end(); ++it)
	{
		eDVBFrontend *fe = it->m_frontend;
		if (!fe || fe->getSlotID() != slot)
			continue;
		eDVBFrontend *sec_fe = fe;
		if (!(not_linked_mask & (1 << slot)))
		{
			long linked_prev_ptr = -1;
			fe->getData(eDVBFrontend::LINKED_PREV_PTR, linked_prev_ptr);
			while (linked_prev_ptr != -1)
			{
				eDVBRegisteredFrontend *linked_fe = (eDVBRegisteredFrontend*) linked_prev_ptr;
				sec_fe = linked_fe->m_frontend;
				sec_fe->getData(eDVBFrontend::LINKED_PREV_PTR, linked_prev_ptr);
			}
		}
		if (root)
			*root = sec_fe;
		return fe;
	}
	return 0;
}

int eDVBSatelliteEquipmentControl::hdsRestoreRotorPosition(int slot, int orbital, int rotor_cmd)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return 0;
	int found = 0;
	/* pozitia pusa sau uitata din Python (miscari manuale, readucerea, pozitia redata): zona unei
	   mutari intrerupte nu mai spune unde e antena */
	s_hds_zona[slot] = hdsrotire::Zona();
	/* urma motorului: pozitia crezuta de dinainte, ca randul sa arate schimbarea */
	int hds_de_la = hdsKnownRotorPosition(slot), hds_de_la_cmd = hdsKnownRotorCmd(slot);
	eSmartPtrList<eDVBRegisteredFrontend> *lists[2] = { &m_avail_frontends, &m_avail_simulate_frontends };
	for (int i = 0; i < 2; ++i)
	{
		eDVBFrontend *root = 0;
		eDVBFrontend *fe = hdsSlotFrontend(*lists[i], slot, m_not_linked_slot_mask, &root);
		if (!fe)
			continue;
		root->setData(eDVBFrontend::ROTOR_POS, orbital);
		root->setData(eDVBFrontend::ROTOR_CMD, rotor_cmd);
		if (root->getSlotID() >= 0 && root->getSlotID() < HDS_MAX_ROTOR_SLOTS)
			s_hds_zona[root->getSlotID()] = hdsrotire::Zona();
		if (fe != root)
		{
			fe->setData(eDVBFrontend::ROTOR_POS, orbital);
			fe->setData(eDVBFrontend::ROTOR_CMD, rotor_cmd);
		}
		if (i == 0)
			found = 1;
	}
	eDebug("[SEC] hds rotor position of slot %d set to %d (cmd %04x)", slot, orbital, rotor_cmd & 0xFFFF);
	if (found)
		hdsurma::pozitieCrezuta(slot, hds_de_la, hds_de_la_cmd, orbital, rotor_cmd);
	return found;
}

void eDVBSatelliteEquipmentControl::hdsMotorCerere(const char *text, int ttl_ms)
{
	hdsurma::anuntaCerere(text, ttl_ms);
}

int eDVBSatelliteEquipmentControl::hdsReaduceAntena(int slot, int orbital)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return -1;
	for (eSmartPtrList<eDVBRegisteredFrontend>::iterator it(m_avail_frontends.begin()); it != m_avail_frontends.end(); ++it)
	{
		eDVBFrontend *fe = it->m_frontend;
		if (!fe || fe->getSlotID() != slot)
			continue;
		if (it->m_inuse <= 0)
			return 0;
		if (!fe->hdsPoateReacorda(orbital))
			return -2;
		/* pozitia uitata (ROTOR_POS si ROTOR_CMD = -1, cu randul ei in urma): prepare() trimite atunci comanda */
		hdsurma::Motiv hds_motiv("readucere dupa pierderea semnalului");
		hdsRestoreRotorPosition(slot, -1, -1);
		return fe->hdsReacordeaza(orbital, "readucere dupa pierderea semnalului") ? -3 : 1;
	}
	return -1;
}

void eDVBSatelliteEquipmentControl::hdsMotorReaducere(int slot, const char *faza, int incercare, int orbital,
	int fara_semnal_ms, int dupa_ms, int mers_ms, int urmatoarea_s, int cod)
{
	hdsurma::readucere(slot, faza, incercare, orbital, hdsKnownRotorPosition(slot), fara_semnal_ms, dupa_ms, mers_ms,
		urmatoarea_s, cod);
}

/* --- HDSatelit (lib/dvb/hdsrotire.h): motorul pe 18 V pe tunerele fara masurarea curentului --- */

void eDVBSatelliteEquipmentControl::hdsSetRotorModel(int slot, int viteza_est_mgrade, int viteza_vest_mgrade)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	s_hds_model[slot].puneViteze(viteza_est_mgrade, viteza_vest_mgrade);
	eDebug("[SEC] hds motor %d: viteza %.2f grade/s spre est, %.2f spre vest", slot, s_hds_model[slot].viteza_est,
		s_hds_model[slot].viteza_vest);
}

void eDVBSatelliteEquipmentControl::hdsSetRotorArc(int slot, int vest_zecimi, int est_zecimi)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	s_hds_model[slot].puneArc(vest_zecimi, est_zecimi);
}

int eDVBSatelliteEquipmentControl::hdsRotorTinereMs(int slot)
{
	return hdsRotorInfoValid(slot) ? m_hds_rotor[slot].tinere_ms : 0;
}

int eDVBSatelliteEquipmentControl::hdsRotireLa18V(int slot)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return 0;
	int gasit = 0;
	for (int i = 0; i <= m_lnbidx && i < (int)(sizeof(m_lnbs) / sizeof(m_lnbs[0])); ++i)
	{
		eDVBSatelliteLNBParameters &lnb = m_lnbs[i];
		if (!(lnb.m_slot_mask & (1 << slot)) || lnb.m_diseqc_parameters.m_diseqc_mode != eDVBSatelliteDiseqcParameters::V1_2)
			continue;
		/* masurarea curentului sau Unicable/JESS: motorul ramane pe drumul vechi */
		if (lnb.m_rotor_parameters.m_inputpower_parameters.m_use || lnb.SatCR_idx != -1)
			return 0;
		gasit = 1;
	}
	return gasit;
}

void eDVBSatelliteEquipmentControl::hdsRotireGata(int slot, const hdsurma::Acordare *acordare)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS || m_hds_rotor[slot].rotire != 1)
		return;
	hdsRotorMove &m = m_hds_rotor[slot];
	m.rotire = 2;
	long tinut = m.start_ms ? (long)(hdsNowMs() - m.start_ms) : -1;
	eDebug("[SEC] hds motor %d: 18 V tinut %ld ms (estimat %d ms), urmeaza tensiunea tintei", slot, tinut, m.tinere_ms);
	hdsurma::tensiuneRotire(slot, "gata", m.tinere_ms, tinut, m.to_orbital, hdsKnownRotorPosition(slot), acordare);
}

void eDVBSatelliteEquipmentControl::hdsSetRotorTransponders(int slot, const char *lista)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	int n = hdsrotire::puneTranspondere(s_hds_tp[slot], lista);
	eDebug("[SEC] hds motor %d: %d transpondere ale satelitilor motorului (paza probei de semnal)", slot, n);
}

int eDVBSatelliteEquipmentControl::hdsRotorTransponders(int slot)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS || !s_hds_tp[slot].pusa)
		return -1;
	return (int)s_hds_tp[slot].lista.size();
}

/* proba de semnal dinaintea comenzii (lib/dvb/hdsrotire.h): pornita = numai ceasul; prinsa si fara semnal = randul
   "proba_semnal" din urma, cu cat a durat. Prinsa: nicio comanda de motor nu pleaca, pozitia crezuta devine tinta
   (UPDATE_CURRENT_ROTORPARAMS urmeaza in secventa). */
void eDVBSatelliteEquipmentControl::hdsProbaSemnal(int slot, int faza, const hdsurma::Acordare *acordare)
{
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS)
		return;
	if (faza == hdsrotire::PROBA_PORNITA)
	{
		s_hds_proba_ms[slot] = hdsNowMs();
		return;
	}
	long durata = s_hds_proba_ms[slot] ? (long)(hdsNowMs() - s_hds_proba_ms[slot]) : -1;
	s_hds_proba_ms[slot] = 0;
	bool prinsa = faza == hdsrotire::PROBA_PRINSA;
	int spre = acordare ? acordare->orbital : (m_hds_rotor[slot].valid ? m_hds_rotor[slot].to_orbital : -1);
	eDebug("[SEC] hds motor %d: proba de semnal pe tinta (%d) %s dupa %ld ms", slot, spre,
		prinsa ? "prinsa, fara comanda de motor" : "fara semnal, urmeaza comanda de motor", durata);
	hdsurma::probaSemnal(slot, prinsa ? "prinsa" : "fara_semnal", hdsrotire::PROBA_PASI * 250L, durata, spre,
		hdsKnownRotorPosition(slot), acordare);
}

int eDVBSatelliteEquipmentControl::hdsForgetRotorPosition(int slot)
{
	return hdsRestoreRotorPosition(slot, -1, -1);
}

int eDVBSatelliteEquipmentControl::hdsKnownRotorPosition(int slot)
{
	eDVBFrontend *root = 0;
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS || !hdsSlotFrontend(m_avail_frontends, slot, m_not_linked_slot_mask, &root))
		return -1;
	long value = -1;
	root->getData(eDVBFrontend::ROTOR_POS, value);
	return (int)value;
}

int eDVBSatelliteEquipmentControl::hdsKnownRotorCmd(int slot)
{
	eDVBFrontend *root = 0;
	if (slot < 0 || slot >= HDS_MAX_ROTOR_SLOTS || !hdsSlotFrontend(m_avail_frontends, slot, m_not_linked_slot_mask, &root))
		return -1;
	long value = -1;
	root->getData(eDVBFrontend::ROTOR_CMD, value);
	return (int)value;
}
