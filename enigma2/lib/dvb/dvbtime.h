/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __LIB_DVB_DVBTIME_H_
#define __LIB_DVB_DVBTIME_H_

#ifndef SWIG

#include <lib/base/eerror.h>
#include <lib/dvb/esection.h>
#include <dvbsi++/time_date_section.h>
#include <map>
#include <set>
#include <string>
#include <utility>

// ==== HDS_CEAS_DECIZIE_H_INCEPUT ====
// HDSatelit: cand se ia ora din transponder. Totul intre aceste doua
// semne e fara efecte (nu citeste ceasul, nu muta nimic, nu scrie in jurnal) si foloseste numai biblioteca standard, ca
// sa poata fi compilat si probat singur pe PC (teste/test_ceas_transpondere.py). eDVBLocalTimeHandler face ce hotaraste.
//  1. Ora de la UN SINGUR multiplex se foloseste pe loc (EPG, bara), dar e PROVIZORIE: inainte poate sari oricat, inapoi
//     nu sub limita de jos (cu TOLERANTA_S).
//  2. Ora devine SIGURA prin NTP (confirmaInternet), printr-un RTC adevarat (rtcCredibil) sau cand DOUA multiplexuri
//     diferite dau aceeasi ora: cel mult TOLERANTA_S intre ele, socotit pe ceasul monoton (ora transponderului minus
//     ceasul monoton).
//  4. Doua multiplexuri de acord castiga si impotriva orei provizorii (si inapoi, dar nu sub limita de jos);
//     multiplexurile care nu se potrivesc cu ele sunt respinse pentru ceas pana la iesirea enigma2 (la fel dupa NTP).
//  5. Dupa ce ora e sigura, un singur multiplex muta ceasul numai daca e de acord cu ora sigura (ancora) si numai cu cel
//     mult TOLERANTA_S fata de ceasul de acum, inainte sau inapoi. Un salt nou numai cu NTP sau cu doua multiplexuri de
//     acord intre ele si nu cu ora sigura (un multiplex de acord cu amandoua nu se numara), si numai daca multiplexurile
//     numai de partea lor nu sunt mai putine decat cele numai de partea orei sigure (la egalitate castiga perechea noua).
//  6. O ora inaintea datei construirii imaginii (minus MARJA_CONSTRUIRE_S) sau dupa ORA_MAXIMA se ignora.
// Doua repere diferite, fiecare o ora de perete la un moment al ceasului monoton (ora lor „de acum” = ora + monoton acum
// - monoton atunci):
//  - limita de jos: ultima ora sigura salvata minus TOLERANTA_S (la pornire: ora salvata e ceasul, pe care punctul 5 il
//    lasa la pana la TOLERANTA_S de ora sigura; daca lipseste, data construirii) sau ora NTP; transponderele nu o muta;
//  - ancora: ora sigura de acum (NTP, RTC sau doua multiplexuri), pentru punctul 5.
// Mersul cristalului: ceasul monoton poate merge cu pana la 100 ppm alaturi de ora reala, deci comparatiile cu un reper
// sau cu o citire mai veche au TOLERANTA_S plus timpul scurs / DERIVA_DIV (8,6 s pe zi). Perechile raman la TOLERANTA_S.
namespace hdsceas
{
	enum Stare
	{
		NECUNOSCUTA = 0,          // la pornire ceasul era inainte de 2004: nicio ora salvata
		SALVATA = 1,              // ora vine din ultima ora salvata (fake-hwclock), nimic nou inca
		PROVIZORIE = 2,           // ora de la un singur multiplex
		SIGURA_INTERNET = 3,      // NTP
		SIGURA_TRANSPONDERE = 4,  // doua multiplexuri diferite de acord
		SIGURA_RTC = 5            // ceas hardware adevarat
	};

	enum Motiv
	{
		NIMIC = 0,
		INAINTE_DE_CONSTRUIRE = 1,  // ignorata: inaintea datei construirii imaginii
		DUPA_LIMITA = 2,            // ignorata: dupa ORA_MAXIMA
		SUB_LIMITA_DE_JOS = 3,      // ignorata: inapoi sub limita de jos
		RESPINS = 4,                // ignorata: multiplex dovedit gresit (de doua alte multiplexuri sau de NTP)
		ASTEAPTA_CONFIRMARE = 5,    // ignorata: un singur multiplex, alta ora decat cea de acum
		PROVIZORIU = 6,             // ceasul mutat, ora provizorie
		DOUA_DE_ACORD = 7,          // ceasul mutat, ora sigura prin doua multiplexuri
		POTRIVIRE = 8,              // ceasul mutat cel mult TOLERANTA_S, ora ramane sigura
		MINORITATE = 9              // ignorata: doua multiplexuri de acord, dar mai multe dau ora sigura de acum
	};

	const long long TOLERANTA_S = 120;
	const long long DERIVA_DIV = 10000;               // 100 ppm: toleranta creste cu timpul scurs / DERIVA_DIV
	const long long MARJA_CONSTRUIRE_S = 7 * 86400;   // data din /etc/image-version poate fi dupa cea reala (fus, ceas de PC)
	const long long ORA_2004 = 1072224000LL;          // ca in constructor: ceasul „valid” pentru enigma2
	const long long ORA_MINIMA_COD = 1789776000LL;    // 2026-09-19 00:00:00 UTC: o saptamana inaintea zilei codului
	const long long ORA_MAXIMA = 2145916799LL;        // 2037-12-31 23:59:59 UTC (nucleul 4.4 pe 32 de biti: 2038-01-19)

	typedef unsigned long long Multiplex;             // spatiul de nume DVB << 32 | TSID << 16 | ONID

	inline bool sigura(int stare) { return stare >= SIGURA_INTERNET; }

	struct Citire
	{
		long long decalaj;                            // ora transponderului minus ceasul monoton
		long long mono;                               // ceasul monoton la citire
		Citire() : decalaj(0), mono(0) {}
		Citire(long long d, long long m) : decalaj(d), mono(m) {}
		bool operator==(const Citire &o) const { return decalaj == o.decalaj && mono == o.mono; }
	};

	struct Ceas
	{
		int stare;
		long long jos_perete, jos_mono;               // limita de jos
		long long ancora_perete, ancora_mono;         // ora sigura (cand stare e sigura)
		long long minim, maxim;                       // limitele absolute
		bool are_sursa;
		Multiplex sursa;                              // multiplexul orei provizorii
		std::map<Multiplex, Citire> citiri;           // ultima citire buna pe multiplex
		std::set<Multiplex> respinse;                 // multiplexuri gresite, ignorate pentru ceas
		std::set<std::pair<Multiplex, int> > scrise;  // (multiplex, motiv) deja scrise in jurnal
	};

	struct Rezultat
	{
		bool muta;           // ceasul se muta la `ora`
		long long ora;
		int motiv;
		bool jurnal;         // un rand in jurnal (o data pe multiplex si motiv; la ora sigura, mereu)
		Multiplex pereche;   // la DOUA_DE_ACORD si MINORITATE: celalalt multiplex
		Ceas nou;            // starea de dupa
	};

	// data construirii folosita: minim din /etc/image-version daca e intre ORA_MINIMA_COD si ORA_MAXIMA, altfel rezerva
	long long minimImagine(long long minim);
	// un RTC e crezut numai daca ora lui e dupa data construirii, inainte de ORA_MAXIMA si la cel mult TOLERANTA_S de ceas
	bool rtcCredibil(long long ora_rtc, long long acum_perete, long long minim);
	// starea de la pornire: ora_salvata = ultima ora sigura salvata (0 daca lipseste), minim = data construirii (0 = rezerva)
	Ceas incepe(long long acum_perete, long long acum_mono, long long ora_salvata, bool rtc, long long minim);
	// o citire TDT/TOT de pe multiplexul mux; acum_perete = ceasul de perete de acum (inainte de citire)
	Rezultat decide(const Ceas &vechi, Multiplex mux, long long ora_tp, long long acum_mono, long long acum_perete);
	// NTP a pus ceasul; respinse_acum primeste multiplexurile respinse acum (poate fi 0)
	Ceas confirmaInternet(const Ceas &vechi, long long acum_perete, long long acum_mono, std::set<Multiplex> *respinse_acum);
	// „YYYY-MM-DD HH:MM:SS” (UTC, formatul fake-hwclock) -> secunde; 0 daca nu se potriveste
	long long oraDinText(const std::string &text);
	// /etc/image-version: „version=0<versiune><YYYYMMDDHHMM>” -> ora commit-ului minus MARJA_CONSTRUIRE_S; 0 daca lipseste
	long long oraDinImageVersion(const std::string &text);
}
// ==== HDS_CEAS_DECIZIE_H_SFARSIT ====

class eDVBChannel;

inline int fromBCD(int bcd)
{
	if ((bcd&0xF0)>=0xA0)
		return -1;
	if ((bcd&0xF)>=0xA)
		return -1;
	return ((bcd&0xF0)>>4)*10+(bcd&0xF);
}

inline int toBCD(int dec)
{
	if (dec >= 100)
		return -1;
	return int(dec/10)*0x10 + dec%10;
}

time_t parseDVBtime(__u8 t1, __u8 t2, __u8 t3, __u8 t4, __u8 t5, __u16 *hash=0);

class TDT: public eGTable
{
	eDVBChannel *chan;
	ePtr<iDVBDemux> demux;
	ePtr<eTimer> m_interval_timer;
	int createTable(unsigned int nr, const __u8 *data, unsigned int max);
	void ready(int);
	int update_count;
public:
	TDT(eDVBChannel *chan, int update_count=0);
	void start();
	void startTimer(int interval);
	int getUpdateCount() { return update_count; }
};

#endif  // SWIG

class eDVBLocalTimeHandler: public sigc::trackable
{
	DECLARE_REF(eDVBLocalTimeHandler);
	struct channel_data
	{
		ePtr<TDT> tdt;
		ePtr<eDVBChannel> channel;
		ePtr<eConnection> m_stateChangedConn;
		int m_prevChannelState;
	};
	bool m_use_dvb_time;
	ePtr<eTimer> m_updateNonTunedTimer;
	friend class TDT;
	std::map<iDVBChannel*, channel_data> m_knownChannels;
	std::map<eDVBChannelID,int> m_timeOffsetMap;
	ePtr<eConnection> m_chanAddedConn;
	bool m_time_ready;
#ifndef SWIG
	// HDSatelit: starea orei (necunoscuta, salvata, provizorie, sigura si de unde), limita
	// de jos, ancora si citirile pe multiplex; hotararile le ia hdsceas::decide (sus, fara efecte).
	hdsceas::Ceas m_hds;
	void hdsJurnal(const hdsceas::Rezultat &r, hdsceas::Multiplex mux, long long ora_tp, long long acum, int stare_inainte);
#endif
	int m_time_difference;
	int m_last_tp_time_difference;
	void DVBChannelAdded(eDVBChannel*);
	void DVBChannelStateChanged(iDVBChannel*);
	void readTimeOffsetData(const char*);
	void writeTimeOffsetData(const char*);
	void updateTime(time_t tp_time, eDVBChannel*, int updateCount);
	void updateNonTuned();
	static eDVBLocalTimeHandler *instance;
#ifdef SWIG
	eDVBLocalTimeHandler();
	~eDVBLocalTimeHandler();
#endif
public:
#ifndef SWIG
	eDVBLocalTimeHandler();
	~eDVBLocalTimeHandler();
#endif
	bool getUseDVBTime() { return m_use_dvb_time; }
	void setUseDVBTime(bool b);
	PSignal0<void> m_timeUpdated;
	bool ready() const { return m_time_ready; }
	// HDSatelit: chemata din Python (Components/HdsCeas.py) dupa ce NTP a pus ora: ora devine
	// sigura (Internet), iar corectiile socotite fata de ora veche se uita.
	void hdsConfirmTime();
	// HDSatelit: starea orei, pentru ecranul „Data si ora” si /ceas: 0 necunoscuta, 1 din
	// ultima ora salvata, 2 provizorie (un singur transponder), 3 sigura (Internet), 4 sigura (doua transpondere),
	// 5 sigura (ceasul receptorului). hdsTimeConfirmed: ora e sigura (3, 4 sau 5); numai atunci se salveaza.
	int hdsTimeState() const;
	bool hdsTimeConfirmed() const;
	static eDVBLocalTimeHandler *getInstance() { return instance; }
};

#endif // __LIB_DVB_DVBTIME_H_
