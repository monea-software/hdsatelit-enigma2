/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvb_frontend_h
#define __dvb_frontend_h

#include <lib/dvb/idvb.h>

class eDVBFrontendParameters: public iDVBFrontendParameters
{
	DECLARE_REF(eDVBFrontendParameters);
	union
	{
		eDVBFrontendParametersSatellite sat;
		eDVBFrontendParametersCable cable;
		eDVBFrontendParametersTerrestrial terrestrial;
	};
	int m_type;
	int m_flags;
public:
	eDVBFrontendParameters();
	~eDVBFrontendParameters()
	{
	}

	SWIG_VOID(RESULT) getSystem(int &SWIG_OUTPUT) const;
	SWIG_VOID(RESULT) getDVBS(eDVBFrontendParametersSatellite &SWIG_OUTPUT) const;
	SWIG_VOID(RESULT) getDVBC(eDVBFrontendParametersCable &SWIG_OUTPUT) const;
	SWIG_VOID(RESULT) getDVBT(eDVBFrontendParametersTerrestrial &SWIG_OUTPUT) const;

	RESULT setDVBS(const eDVBFrontendParametersSatellite &p, bool no_rotor_command_on_tune=false);
	RESULT setDVBC(const eDVBFrontendParametersCable &p);
	RESULT setDVBT(const eDVBFrontendParametersTerrestrial &p);
	SWIG_VOID(RESULT) getFlags(unsigned int &SWIG_NAMED_OUTPUT(flags)) const { flags = m_flags; return 0; }
	RESULT setFlags(unsigned int flags) { m_flags = flags; return 0; }
#ifndef SWIG
	RESULT calculateDifference(const iDVBFrontendParameters *parm, int &, bool exact) const;

	RESULT getHash(unsigned long &) const;
	RESULT calcLockTimeout(unsigned int &) const;
#endif
};

/* HDSatelit: contoarele citirilor starii tunerelor (lib/dvb/hdscitirifrontend.h), din Python:
   enigma.getFrontendReadCounts() -> {"cereri", "din_memorie", "ioctl", "ioctl_direct", "erori", "us_ioctl", "ttl_ms",
   "ttl_lent_ms"}; numere pe 32 de biti fara semn care se dau peste cap (se folosesc diferentele) */
PyObject *getFrontendReadCounts();

#ifndef SWIG

#include <lib/dvb/sec.h>
#include <lib/dvb/hdsurmamotor.h>
#include <lib/dvb/hdsjurnaltuner.h>
#include <lib/dvb/hdscitirifrontend.h>
class eSecCommandList;

class eDVBFrontend: public iDVBFrontend, public sigc::trackable
{
public:
	/* Marcaje monotone, fara citiri suplimentare din driver. SEC include confirmarea motorului. */
	struct TimpiZap
	{
		long long pornire_ms, sec_start_ms, sec_gata_ms, comanda_ms, lock_ms;
		TimpiZap(): pornire_ms(0), sec_start_ms(0), sec_gata_ms(0), comanda_ms(0), lock_ms(0) {}
	};
	enum {
		NEW_CSW,
		NEW_UCSW,
		NEW_TONEBURST,
		CSW,                  // state of the committed switch
		UCSW,                 // state of the uncommitted switch
		TONEBURST,            // current state of toneburst switch
		NEW_ROTOR_CMD,        // prev sent rotor cmd
		NEW_ROTOR_POS,        // new rotor position (not validated)
		ROTOR_CMD,            // completed rotor cmd (finalized)
		ROTOR_POS,            // current rotor position
		LINKED_PREV_PTR,      // prev double linked list (for linked FEs)
		LINKED_NEXT_PTR,      // next double linked list (for linked FEs)
		SATPOS_DEPENDS_PTR,   // pointer to FE with configured rotor (with twin/quattro lnb)
		FREQ_OFFSET,          // current frequency offset
		CUR_VOLTAGE,          // current voltage
		CUR_TONE,             // current continuous tone
		SATCR,                // current SatCR
		NUM_DATA_ENTRIES
	};
	sigc::signal<void(iDVBFrontend*)> m_stateChanged;
private:
	DECLARE_REF(eDVBFrontend);
	bool m_simulate;
	bool m_enabled;
	int m_type;
	eDVBFrontend *m_simulate_fe; // only used to set frontend type in dvb.cpp
	int m_dvbid;
	int m_slotid;
	int m_fd;
	bool m_rotor_mode;
	bool m_need_rotor_workaround;
	bool m_can_handle_dvbs2;
	int m_delsys_types; // one bit per iDVBFrontend type this tuner can switch to (DTV_ENUM_DELSYS)
	bool m_multistream; // FE_CAN_MULTISTREAM: filtrul de flux (ISI) si PLS-ul se pot cere
	bool m_dvbt2;       // DTV_ENUM_DELSYS are SYS_DVBT2 (numai pentru jurnal: acordarea DVB-T2 se incearca oricum)
	int m_dvb_api;      // DTV_API_VERSION citit din frontend (major << 8 | minor), 0 = necitit
	int m_hds_fbc_set;  // grupul confirmat de driver, -1 fara FBC
	char m_filename[128];
	char m_description[128];
#if HAVE_DVB_API_VERSION < 3
	int m_secfd;
	char m_sec_filename[128];
#endif
	FRONTENDPARAMETERS parm;
	union {
		eDVBFrontendParametersSatellite sat;
		eDVBFrontendParametersCable cab;
		eDVBFrontendParametersTerrestrial ter;
	} oparm;

	int m_state;
	ePtr<iDVBSatelliteEquipmentControl> m_sec;
	ePtr<eSocketNotifier> m_sn;
	int m_tuning;
	ePtr<eTimer> m_timeout, m_tuneTimer;

	eSecCommandList m_sec_sequence;

	long m_data[NUM_DATA_ENTRIES];

	int m_idleInputpower[2];  // 13V .. 18V
	int m_runningInputpower;

	int m_timeoutCount; // needed for timeout
	int m_retryCount; // diseqc retry for rotor
	bool m_hds_rotor_locked; // HDSatelit: IF_TUNER_LOCKED_GOTO a gasit semnalul dupa miscarea motorului
	/* HDSatelit (urma motorului, lib/dvb/hdsurmamotor.h): ultima acordare a tunerului, cine a cerut-o si ce a hotarat
	   sec.cpp pentru motor; comenzile secventei o poarta cu ele in urma */
	hdsurma::Acordare m_hds_acordare;
	hdsjtuner::Stare m_hds_jurnal; // HDSatelit: jurnalul tunerului (lib/dvb/hdsjurnaltuner.h)
	TimpiZap m_hds_timpi_zap;
	/* HDSatelit (0.7.4, zap-ul pe cablu): ce a pus enigma2 pe descriptorul deschis acum al tunerului, ca sa nu se mai
	   trimita la fiecare acordare: sistemul de livrare (SYS_DVBC_ANNEX_A, SYS_DVBT, SYS_DVBT2; -1 = nestiut) si
	   alimentarea antenei oprita ("off" scris in active_antenna_power). Se uita la deschidere, la inchidere si la un
	   refuz al driverului. Sistemul nu-l poate schimba alt proces cat timp descriptorul e deschis (dvb-core lasa un
	   singur descriptor cu scriere pe tuner si refuza FE_SET_PROPERTY pe unul numai de citire); fisierul antenei il
	   scrie, in imagine, numai setVoltage. */
	int m_hds_sistem_pus;
	bool m_hds_antena_oprita;
	/* HDSatelit: memoria citirilor starii (lib/dvb/hdscitirifrontend.h): o citire a fiecarei valori pe secunda, impartita
	   de toti cititorii; direct = fara memorie (bucla SEC, timeout()) */
	hdscitiri::Memorie m_hds_citiri;
	unsigned int hdsCitesteBrut(int fel, bool direct, int &err);
	int hdsCiteste(int type, bool direct);

	void feEvent(int);
	void timeout();
	void tuneLoop();  // called by m_tuneTimer
	int tuneLoopInt();
	void setFrontend(bool recvEvents=true);
	void hdsComandaTuner(bool recvEvents);
	/* HDSatelit (0.7.4, viteza zap): pasii secventei SEC care nu asteapta, rulati pe loc din tune() (frontend.cpp) */
	void hdsSecPeLoc();
	/* HDSatelit (0.7.4, scanarea): la o acordare a cautarii (motivul "scanare") pe satelit cu asteptarea de 5 s, dupa
	   HDS_SCAN_VERIFICARE_MS fara semnal prins se citeste starea; fara semnal si fara purtatoare, acordarea se da pierduta
	   atunci (timeout()), nu dupa 5 s (frontend.cpp, hdsScanVerifica) */
	enum { HDS_SCAN_VERIFICARE_MS = 3000 };
	bool m_hds_e_scanare;
	ePtr<eTimer> m_hds_scan_verificare;
	void hdsScanVerifica();
	bool setSecSequencePos(int steps);
	RESULT switchDeliverySystem(int type, bool t2 = false);
	static int PriorityOrder;
public:
		/* devicename: dispozitivul deschis in locul /dev/dvb/adapter<adap>/frontend<fe> (puntea vtuner: frontend-ul virtual
		   al placii se acordeaza prin tunerul USB adevarat, lib/dvb/hdsvtuner.cpp); NULL = cel obisnuit */
	eDVBFrontend(int adap, int fe, int &ok, bool simulate=false, eDVBFrontend *simulate_fe=NULL, const char *devicename=NULL);
	virtual ~eDVBFrontend();

	int readInputpower();
	bool hdsSameFbcSet(const eDVBFrontend &other) const
	{
		return m_type == feSatellite && other.m_type == feSatellite
			&& m_hds_fbc_set >= 0 && m_hds_fbc_set == other.m_hds_fbc_set;
	}
	RESULT getFrontendType(int &type);
	RESULT tune(const iDVBFrontendParameters &where);
	RESULT prepare_sat(const eDVBFrontendParametersSatellite &, unsigned int timeout);
	RESULT prepare_cable(const eDVBFrontendParametersCable &);
	RESULT prepare_terrestrial(const eDVBFrontendParametersTerrestrial &);
	RESULT connectStateChange(const sigc::slot<void(iDVBFrontend*)> &stateChange, ePtr<eConnection> &connection);
	RESULT getState(int &state);
	RESULT setTone(int tone);
	RESULT setVoltage(int voltage);
	RESULT sendDiseqc(const eDVBDiseqcCommand &diseqc);
	/* HDSatelit (urma motorului): trimiterea cu acordarea care a pus-o (secventa SEC) sau 0 (trimitere directa) */
	RESULT hdsSendDiseqc(const eDVBDiseqcCommand &diseqc, const hdsurma::Acordare *acordare);
	hdsurma::Acordare &hdsAcordare() { return m_hds_acordare; }
	const TimpiZap &hdsTimpiZap() const { return m_hds_timpi_zap; }
	/* HDSatelit (0.7.4, viteza zap): false cand exista /tmp/hds-zap-vechi; atunci zap-ul merge ca in 0.7.3 (secventa SEC
	   numai prin ceas, PMT-ul numai dupa PAT). Pentru masurarea inainte/dupa pe aceeasi imagine; fisierul nu-l pune nimeni
	   din imagine. */
	static bool hdsZapRapid();
	/* HDSatelit: acordul de acum din nou, pe ultima acordare reusita de satelit (oparm.sat), ca
	   reacordarea nucleului dupa pierderea semnalului; `motiv` intra in urma motorului. hdsPoateReacorda: tunerul e
	   deschis si ultima lui acordare e pe `orbital`. hdsReacordeaza: 0 = acordat, -2 = nu se poate, altfel codul tune() */
	bool hdsPoateReacorda(int orbital);
	int hdsReacordeaza(int orbital, const char *motiv);
	RESULT sendToneburst(int burst);
	RESULT setSEC(iDVBSatelliteEquipmentControl *sec);
	RESULT setSecSequence(eSecCommandList &list);
	RESULT getData(int num, long &data);
	RESULT setData(int num, long val);

	int readFrontendData(int type); // bitErrorRate, signalPower, signalQualitydB, signalQuality, locked, synced
	void getFrontendStatus(ePyObject dest);
	void getTransponderData(ePyObject dest, bool original);
	void getFrontendData(ePyObject dest);

	int isCompatibleWith(ePtr<iDVBFrontendParameters> &feparm);
	int getDVBID() { return m_dvbid; }
	int getSlotID() { return m_slotid; }
	bool setSlotInfo(ePyObject obj); // get a tuple (slotid, slotdescr)
	static void setTypePriorityOrder(int val) { PriorityOrder = val; }
	static int getTypePriorityOrder() { return PriorityOrder; }

	void reopenFrontend();
	int openFrontend();
	int closeFrontend(bool force=false, bool no_delayed=false);
	const char *getDescription() const { return m_description; }
	bool is_simulate() const { return m_simulate; }
};

#endif // SWIG
#endif
