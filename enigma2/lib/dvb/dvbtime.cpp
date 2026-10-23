/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/dvb/dvbtime.h>
#include <lib/dvb/dvb.h>

#include <sys/ioctl.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <time.h>

// defines for DM7000 / DM7020
#define FP_IOCTL_SET_RTC         0x101
#define FP_IOCTL_GET_RTC         0x102

#define TIME_UPDATE_INTERVAL (30*60*1000)

// HDSatelit: ultima ora SIGURA salvata, scrisa numai de Components/HdsCeas.py (NTP, doua
// transpondere sau RTC), in formatul fake-hwclock. Nu e /etc/fake-hwclock.data: acela e ceasul de pornire si il poate
// scrie oricine cu orice ora (`fake-hwclock save` din consola; scriptul de oprire K25fake-hwclock, pe care imaginea
// noastra nu il mai are: meta-local, fake-hwclock.bbappend). Fisierul acesta are un singur scriitor, deci e limita de jos.
#define HDS_ORA_SIGURA "/etc/hds-ora-sigura.data"
#define HDS_IMAGE_VERSION "/etc/image-version"

// ==== HDS_CEAS_DECIZIE_CPP_INCEPUT ====
// HDSatelit: hotararile, fara efecte (vezi dvbtime.h, intre semnele HDS_CEAS_DECIZIE_H).
namespace hdsceas
{
	static long long diferentaAbs(long long a, long long b)
	{
		return a > b ? a - b : b - a;
	}

	// zile de la 1970-01-01 pana la data gregoriana data (algoritmul „days from civil” al lui Howard Hinnant)
	static long long zileDinCivil(long long an, long long luna, long long zi)
	{
		an -= luna <= 2 ? 1 : 0;
		const long long era = (an >= 0 ? an : an - 399) / 400;
		const long long ane = an - era * 400;
		const long long zia = (153 * (luna + (luna > 2 ? -3 : 9)) + 2) / 5 + zi - 1;
		const long long zie = ane * 365 + ane / 4 - ane / 100 + zia;
		return era * 146097 + zie - 719468;
	}

	static bool dataBuna(long long an, long long luna, long long zi, long long ora, long long minut, long long secunda)
	{
		static const int zile[12] = { 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
		if (an < 1970 || an > 9999 || luna < 1 || luna > 12 || zi < 1 || zi > zile[luna - 1])
			return false;
		if (luna == 2 && zi == 29 && !((an % 4 == 0 && an % 100 != 0) || an % 400 == 0))
			return false;
		return ora >= 0 && ora <= 23 && minut >= 0 && minut <= 59 && secunda >= 0 && secunda <= 59;
	}

	static bool cifre(const std::string &text, size_t de, size_t cate, long long &valoare)
	{
		if (de + cate > text.size())
			return false;
		valoare = 0;
		for (size_t i = de; i < de + cate; ++i)
		{
			if (text[i] < '0' || text[i] > '9')
				return false;
			valoare = valoare * 10 + (text[i] - '0');
		}
		return true;
	}

	long long oraDinText(const std::string &text)
	{
		std::string t(text);
		while (!t.empty() && (t[t.size() - 1] == '\n' || t[t.size() - 1] == '\r' || t[t.size() - 1] == ' '))
			t.erase(t.size() - 1);
		if (t.size() != 19 || t[4] != '-' || t[7] != '-' || t[10] != ' ' || t[13] != ':' || t[16] != ':')
			return 0;
		long long an, luna, zi, ora, minut, secunda;
		if (!cifre(t, 0, 4, an) || !cifre(t, 5, 2, luna) || !cifre(t, 8, 2, zi) || !cifre(t, 11, 2, ora) ||
			!cifre(t, 14, 2, minut) || !cifre(t, 17, 2, secunda) || !dataBuna(an, luna, zi, ora, minut, secunda))
			return 0;
		return zileDinCivil(an, luna, zi) * 86400 + ora * 3600 + minut * 60 + secunda;
	}

	long long oraDinImageVersion(const std::string &text)
	{
		// randul „version=0<versiune><YYYYMMDDHHMM>” (Makefile.am): data commit-ului sursei, in fusul celui care a comis
		size_t p = text.find("version=");
		while (p != std::string::npos && p != 0 && text[p - 1] != '\n')
			p = text.find("version=", p + 1);
		if (p == std::string::npos)
			return 0;
		const size_t inceput = p + 8;
		size_t sfarsit = inceput;
		while (sfarsit < text.size() && text[sfarsit] >= '0' && text[sfarsit] <= '9')
			++sfarsit;
		if (sfarsit - inceput < 13)
			return 0;
		const size_t d = sfarsit - 12;
		long long an, luna, zi, ora, minut;
		if (!cifre(text, d, 4, an) || !cifre(text, d + 4, 2, luna) || !cifre(text, d + 6, 2, zi) ||
			!cifre(text, d + 8, 2, ora) || !cifre(text, d + 10, 2, minut) || !dataBuna(an, luna, zi, ora, minut, 0))
			return 0;
		// o saptamana mai devreme: fusul orar al celui care a comis nu se stie, iar ceasul PC-ului lui poate merge inainte
		return zileDinCivil(an, luna, zi) * 86400 + ora * 3600 + minut * 60 - MARJA_CONSTRUIRE_S;
	}

	// toleranta fata de un reper sau o citire de acum `scurs` secunde (ceasul monoton): TOLERANTA_S plus 100 ppm
	static long long toleranta(long long scurs)
	{
		return TOLERANTA_S + diferentaAbs(scurs, 0) / DERIVA_DIV;
	}

	long long minimImagine(long long minim)
	{
		return (minim > ORA_MINIMA_COD && minim <= ORA_MAXIMA) ? minim : ORA_MINIMA_COD;
	}

	bool rtcCredibil(long long ora_rtc, long long acum_perete, long long minim)
	{
		return ora_rtc >= minimImagine(minim) && ora_rtc <= ORA_MAXIMA && diferentaAbs(ora_rtc, acum_perete) <= TOLERANTA_S;
	}

	Ceas incepe(long long acum_perete, long long acum_mono, long long ora_salvata, bool rtc, long long minim)
	{
		Ceas c;
		c.minim = minimImagine(minim);
		c.maxim = ORA_MAXIMA;
		c.are_sursa = false;
		c.sursa = 0;
		c.ancora_perete = acum_perete;
		c.ancora_mono = acum_mono;
		c.jos_mono = acum_mono;
		const bool salvata_buna = ora_salvata >= ORA_2004 && ora_salvata <= ORA_MAXIMA;
		// ora sigura salvata e ceasul de atunci, pe care un singur multiplex il poate muta cu pana la TOLERANTA_S fata de ora
		// sigura (punctul 5): limita de jos e cu TOLERANTA_S mai devreme, iar decide mai adauga TOLERANTA_S (punctul 1)
		const long long jos_salvata = ora_salvata - TOLERANTA_S;
		if (acum_perete < ORA_2004)
		{
			c.stare = NECUNOSCUTA;
			c.jos_perete = salvata_buna ? jos_salvata : 0;
		}
		else if (rtc && acum_perete >= c.minim)
		{
			c.stare = SIGURA_RTC;
			c.jos_perete = acum_perete;
		}
		else
		{
			// ora de acum vine din fake-hwclock, deci nu e o limita de jos sigura (se poate scrie si cu mana, cu `fake-hwclock
			// save`): limita de jos e ultima ora sigura salvata de HdsCeas, cand exista; altfel data construirii (mai jos)
			c.stare = SALVATA;
			c.jos_perete = salvata_buna ? jos_salvata : c.minim;
		}
		if (c.jos_perete < c.minim)
			c.jos_perete = c.minim;
		return c;
	}

	static Rezultat ignora(Rezultat &r, Multiplex mux, int motiv)
	{
		r.motiv = motiv;
		r.jurnal = r.nou.scrise.insert(std::make_pair(mux, motiv)).second;
		return r;
	}

	// o ora data ca decalaj (ora minus ceasul monoton) la monotonul `mono` e de acord cu ora sigura (ancora)?
	static bool deAcordCuAncora(const Ceas &c, long long decalaj, long long mono)
	{
		return diferentaAbs(decalaj, c.ancora_perete - c.ancora_mono) <= toleranta(mono - c.ancora_mono);
	}

	// alt multiplex a dat aceeasi ora (cel mult TOLERANTA_S, pe ceasul monoton)?
	static bool gasestePereche(const Ceas &c, Multiplex mux, long long decalaj, Multiplex &pereche)
	{
		for (std::map<Multiplex, Citire>::const_iterator it = c.citiri.begin(); it != c.citiri.end(); ++it)
		{
			if (it->first != mux && diferentaAbs(it->second.decalaj, decalaj) <= TOLERANTA_S)
			{
				pereche = it->first;
				return true;
			}
		}
		return false;
	}

	// multiplexurile care nu se potrivesc cu `decalaj` (ora buna minus ceasul monoton, la `acum_mono`) sunt respinse pentru
	// ceas; o citire mai veche are si toleranta mersului cristalului
	static void respingeCeleLalte(Ceas &c, long long decalaj, long long acum_mono, std::set<Multiplex> *respinse_acum)
	{
		for (std::map<Multiplex, Citire>::iterator it = c.citiri.begin(); it != c.citiri.end(); )
		{
			if (diferentaAbs(it->second.decalaj, decalaj) > toleranta(acum_mono - it->second.mono))
			{
				c.respinse.insert(it->first);
				if (respinse_acum)
					respinse_acum->insert(it->first);
				c.citiri.erase(it++);
			}
			else
				++it;
		}
	}

	static Rezultat douaDeAcord(Rezultat &r, long long ora_tp, long long acum_mono)
	{
		Ceas &c = r.nou;
		c.stare = SIGURA_TRANSPONDERE;
		c.ancora_perete = ora_tp;
		c.ancora_mono = acum_mono;
		c.are_sursa = false;
		respingeCeleLalte(c, ora_tp - acum_mono, acum_mono, 0);
		r.muta = true;
		r.ora = ora_tp;
		r.motiv = DOUA_DE_ACORD;
		r.jurnal = true;
		return r;
	}

	Rezultat decide(const Ceas &vechi, Multiplex mux, long long ora_tp, long long acum_mono, long long acum_perete)
	{
		Rezultat r;
		r.muta = false;
		r.ora = 0;
		r.motiv = NIMIC;
		r.jurnal = false;
		r.pereche = 0;
		r.nou = vechi;
		Ceas &c = r.nou;
		if (ora_tp < c.minim)
			return ignora(r, mux, INAINTE_DE_CONSTRUIRE);
		if (ora_tp > c.maxim)
			return ignora(r, mux, DUPA_LIMITA);
		if (c.respinse.count(mux))
			return ignora(r, mux, RESPINS);
		const long long scurs_jos = acum_mono - c.jos_mono;
		if (ora_tp < c.jos_perete + scurs_jos - toleranta(scurs_jos))
			return ignora(r, mux, SUB_LIMITA_DE_JOS);

		const long long decalaj = ora_tp - acum_mono;
		c.citiri[mux] = Citire(decalaj, acum_mono);

		if (sigura(c.stare))
		{
			// 5. de acord cu ora sigura: potrivire, cel mult TOLERANTA_S fata de ceasul de acum. Daca ceasul a fost mutat de
			// altcineva in afara orei sigure, o potrivire il aduce inapoi; daca citirea e mai aproape de ora sigura decat
			// ceasul, dar la peste TOLERANTA_S de el, ceasul face un pas de TOLERANTA_S spre ea (nu ramane blocat).
			if (deAcordCuAncora(c, decalaj, acum_mono))
			{
				r.ora = ora_tp;
				if (diferentaAbs(ora_tp, acum_perete) > TOLERANTA_S && deAcordCuAncora(c, acum_perete - acum_mono, acum_mono))
				{
					const long long sigura_acum = c.ancora_perete + (acum_mono - c.ancora_mono);
					if (diferentaAbs(ora_tp, sigura_acum) >= diferentaAbs(acum_perete, sigura_acum))
						return ignora(r, mux, ASTEAPTA_CONFIRMARE);
					r.ora = ora_tp > acum_perete ? acum_perete + TOLERANTA_S : acum_perete - TOLERANTA_S;
				}
				r.muta = true;
				r.motiv = POTRIVIRE;
				return r;
			}
			// alta ora decat cea sigura: un salt nou numai cu doua multiplexuri de acord, si numai daca multiplexurile numai
			// de partea lor nu sunt mai putine decat cele numai de partea orei sigure (la egalitate castiga perechea noua)
			if (!gasestePereche(c, mux, decalaj, r.pereche))
				return ignora(r, mux, ASTEAPTA_CONFIRMARE);
			int noi = 0, vechi_ = 0;
			for (std::map<Multiplex, Citire>::const_iterator it = c.citiri.begin(); it != c.citiri.end(); ++it)
			{
				const bool cu_ancora = deAcordCuAncora(c, it->second.decalaj, it->second.mono);
				const bool cu_perechea = diferentaAbs(it->second.decalaj, decalaj) <= TOLERANTA_S;
				if (cu_perechea && !cu_ancora)
					++noi;
				if (cu_ancora && !cu_perechea)
					++vechi_;
			}
			// punctul 4: amandoua trebuie sa fie de alta parte decat ora sigura; un multiplex de acord cu ambele nu conteaza
			if (noi < 2)
				return ignora(r, mux, ASTEAPTA_CONFIRMARE);
			if (noi < vechi_)
				return ignora(r, mux, MINORITATE);
			return douaDeAcord(r, ora_tp, acum_mono);
		}
		// 2 si 4. ora nesigura: doua multiplexuri de acord o fac sigura, si impotriva orei provizorii
		if (gasestePereche(c, mux, decalaj, r.pereche))
			return douaDeAcord(r, ora_tp, acum_mono);
		// un singur multiplex care nu se potriveste cu ora provizorie de la alt multiplex: asteapta
		if (c.stare == PROVIZORIE && c.are_sursa && c.sursa != mux)
			return ignora(r, mux, ASTEAPTA_CONFIRMARE);
		// 1. primul multiplex (sau acelasi): ora provizorie
		c.stare = PROVIZORIE;
		c.are_sursa = true;
		c.sursa = mux;
		r.muta = true;
		r.ora = ora_tp;
		r.motiv = PROVIZORIU;
		r.jurnal = c.scrise.insert(std::make_pair(mux, (int)PROVIZORIU)).second;
		return r;
	}

	Ceas confirmaInternet(const Ceas &vechi, long long acum_perete, long long acum_mono, std::set<Multiplex> *respinse_acum)
	{
		Ceas c(vechi);
		c.stare = SIGURA_INTERNET;
		c.jos_perete = c.ancora_perete = acum_perete;
		c.jos_mono = c.ancora_mono = acum_mono;
		c.are_sursa = false;
		std::set<Multiplex> acum;
		respingeCeleLalte(c, acum_perete - acum_mono, acum_mono, &acum);
		for (std::set<Multiplex>::const_iterator it = acum.begin(); it != acum.end(); ++it)
			c.scrise.insert(std::make_pair(*it, (int)RESPINS));   // scrise in jurnal de cel care cheama
		if (respinse_acum)
			respinse_acum->insert(acum.begin(), acum.end());
		return c;
	}
}
// ==== HDS_CEAS_DECIZIE_CPP_SFARSIT ====

static long long hdsMonoton()
{
	timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
		return 0;
	return ts.tv_sec;
}

static std::string hdsCitesteFisier(const char *cale)
{
	std::string text;
	FILE *f = fopen(cale, "r");
	if (f)
	{
		char buf[256];
		size_t n = fread(buf, 1, sizeof(buf) - 1, f);
		text.assign(buf, n);
		fclose(f);
	}
	return text;
}

static hdsceas::Multiplex hdsMultiplex(const eDVBChannelID &id)
{
	return ((hdsceas::Multiplex)(unsigned int)id.dvbnamespace.get() << 32) |
		((hdsceas::Multiplex)(id.transport_stream_id.get() & 0xffff) << 16) |
		(hdsceas::Multiplex)(id.original_network_id.get() & 0xffff);
}

static std::string hdsTextMultiplex(hdsceas::Multiplex mux)
{
	char text[32];
	snprintf(text, sizeof(text), "%08x:%04x:%04x", (unsigned int)(mux >> 32), (unsigned int)((mux >> 16) & 0xffff),
		(unsigned int)(mux & 0xffff));
	return text;
}

static std::string hdsTextOra(long long ora)
{
	char text[32];
	time_t t = (time_t)ora;
	tm u;
	if (!gmtime_r(&t, &u) || !strftime(text, sizeof(text), "%Y-%m-%d %H:%M:%S", &u))
		return "?";
	return text;
}

static const char *hdsNumeStare(int stare)
{
	switch (stare)
	{
		case hdsceas::NECUNOSCUTA: return "necunoscuta";
		case hdsceas::SALVATA: return "din ultima ora salvata";
		case hdsceas::PROVIZORIE: return "provizorie";
		case hdsceas::SIGURA_INTERNET: return "sigura (Internet)";
		case hdsceas::SIGURA_TRANSPONDERE: return "sigura (doua transpondere)";
		case hdsceas::SIGURA_RTC: return "sigura (ceasul receptorului)";
	}
	return "?";
}

static time_t prev_time;

void setRTC(time_t time)
{
	FILE *f = fopen("/proc/stb/fp/rtc", "w");
	if (f)
	{
		if (fprintf(f, "%u", (unsigned int)time))
			prev_time = time;
		else
			eDebug("write /proc/stb/fp/rtc failed (%m)");
		fclose(f);
	}
	else
	{
		int fd = open("/dev/dbox/fp0", O_RDWR);
		if ( fd >= 0 )
		{
			if ( ::ioctl(fd, FP_IOCTL_SET_RTC, (void*)&time ) < 0 )
				eDebug("FP_IOCTL_SET_RTC failed(%m)");
			else
				prev_time = time;
			close(fd);
		}
	}
}

time_t getRTC()
{
	time_t rtc_time=0;
	FILE *f = fopen("/proc/stb/fp/rtc", "r");
	if (f)
	{
		// sanity check to detect corrupt atmel firmware
		unsigned int tmp;
		if (fscanf(f, "%u", &tmp) != 1)
			eDebug("read /proc/stb/fp/rtc failed (%m)");
		else
			rtc_time=tmp;
		fclose(f);
	}
	else
	{
		int fd = open("/dev/dbox/fp0", O_RDWR);
		if ( fd >= 0 )
		{
			if ( ::ioctl(fd, FP_IOCTL_GET_RTC, (void*)&rtc_time ) < 0 )
				eDebug("FP_IOCTL_GET_RTC failed(%m)");
			close(fd);
		}
	}
	return rtc_time != prev_time ? rtc_time : 0;
}

time_t parseDVBtime(__u8 t1, __u8 t2, __u8 t3, __u8 t4, __u8 t5, __u16 *hash)
{
	tm t;
	t.tm_sec=fromBCD(t5);
	t.tm_min=fromBCD(t4);
	t.tm_hour=fromBCD(t3);
	int mjd=(t1<<8)|t2;
	int k;

	t.tm_year = (int) ((mjd - 15078.2) / 365.25);
	t.tm_mon = (int) ((mjd - 14956.1 - (int)(t.tm_year * 365.25)) / 30.6001);
	t.tm_mday = (int) (mjd - 14956 - (int)(t.tm_year * 365.25) - (int)(t.tm_mon * 30.6001));
	k = (t.tm_mon == 14 || t.tm_mon == 15) ? 1 : 0;
	t.tm_year = t.tm_year + k;
	t.tm_mon = t.tm_mon - 1 - k * 12;
	t.tm_mon--;

	t.tm_isdst =  0;
	t.tm_gmtoff = 0;

	if (hash) {
		*hash = t.tm_hour * 60 + t.tm_min;
		*hash |= t.tm_mday << 11;
	}

	return timegm(&t);
}

TDT::TDT(eDVBChannel *chan, int update_count)
	:chan(chan), m_interval_timer(eTimer::create()), update_count(update_count)
{
	CONNECT(tableReady, TDT::ready);
	CONNECT(m_interval_timer->timeout, TDT::start);
	if (chan)
		chan->getDemux(demux, 0);
}

void TDT::ready(int error)
{
	eDVBLocalTimeHandler::getInstance()->updateTime(error, chan, ++update_count);
}

int TDT::createTable(unsigned int nr, const __u8 *data, unsigned int max)
{
	if ( data && (data[0] == 0x70 || data[0] == 0x73 ))
	{
		int length = ((data[1] & 0x0F) << 8) | data[2];
		if ( length >= 5 )
		{
			time_t tptime = parseDVBtime(data[3], data[4], data[5], data[6], data[7]);
			if (tptime && tptime != -1)
				eDVBLocalTimeHandler::getInstance()->updateTime(tptime, chan, update_count);
			error=0;
			return 1;
		}
	}
	return 0;
}

void TDT::start()
{
	if ( chan )
	{
		eDVBTableSpec spec;
		spec.pid = TimeAndDateSection::PID;
		spec.tid = TimeAndDateSection::TID;
		spec.tid_mask = 0xFC;
		spec.timeout = TimeAndDateSection::TIMEOUT;
		spec.flags= eDVBTableSpec::tfAnyVersion |
					eDVBTableSpec::tfHaveTID |
					eDVBTableSpec::tfHaveTIDMask |
					eDVBTableSpec::tfHaveTimeout;
		if ( demux )
			eGTable::start( demux, spec );
	}
}

void TDT::startTimer( int interval )
{
	m_interval_timer->start(interval, true);
}

eDVBLocalTimeHandler *eDVBLocalTimeHandler::instance;
DEFINE_REF(eDVBLocalTimeHandler);

eDVBLocalTimeHandler::eDVBLocalTimeHandler()
	:m_use_dvb_time(false), m_updateNonTunedTimer(eTimer::create(eApp)), m_time_ready(false)
{
	if ( !instance )
		instance=this;
	// HDSatelit: starea de pornire. Numai un RTC adevarat face ora sigura de la pornire (dupa
	// data construirii si la cel mult 120 s de ceas: un pseudo-RTC de panou ramas in urma dupa o pana de curent nu e
	// crezut); fara RTC (/proc/stb/fp/rtc si /dev/dbox/fp0 lipsesc pe Viper 4K V20) ora vine din fake-hwclock, e nesigura,
	// iar limita de jos e ultima ora sigura salvata (HDS_ORA_SIGURA) sau, daca lipseste, data construirii.
	const time_t la_pornire = time(0);
	const long long minim = hdsceas::oraDinImageVersion(hdsCitesteFisier(HDS_IMAGE_VERSION));
	const time_t ora_rtc = la_pornire >= 1072224000 ? getRTC() : 0;
	const bool rtc = ora_rtc != 0 && hdsceas::rtcCredibil(ora_rtc, la_pornire, minim);
	if (ora_rtc != 0 && !rtc)
		eDebug("[eDVBLocalTimerHandler] RTC necrezut pentru ora sigura: %s UTC, ceasul %s UTC", hdsTextOra(ora_rtc).c_str(),
			hdsTextOra(la_pornire).c_str());
	const long long salvata = hdsceas::oraDinText(hdsCitesteFisier(HDS_ORA_SIGURA));
	m_hds = hdsceas::incepe(la_pornire, hdsMonoton(), salvata, rtc, minim);
	ePtr<eDVBResourceManager> res_mgr;
	eDVBResourceManager::getInstance(res_mgr);
	if (!res_mgr)
		eDebug("[eDVBLocalTimerHandler] no resource manager !!!!!!!");
	else
	{
		res_mgr->connectChannelAdded(sigc::mem_fun(*this,&eDVBLocalTimeHandler::DVBChannelAdded), m_chanAddedConn);
		time_t now = time(0);
		if ( now < 1072224000 ) // 01.01.2004
			eDebug("RTC not ready... wait for transponder time");
		else // inform all who's waiting for valid system time..
		{
			eDebug("Use valid Linux Time :) (RTC?)");
			m_time_ready = true;
			if (!hdsceas::sigura(m_hds.stare))
				eDebug("[eDVBLocalTimerHandler] fara RTC: ora %s, nesigura; limita de jos %s UTC (ora sigura salvata: %s)",
					hdsNumeStare(m_hds.stare), hdsTextOra(m_hds.jos_perete).c_str(),
					salvata ? hdsTextOra(salvata).c_str() : "lipseste");
			/*emit*/ m_timeUpdated();
		}
	}
	CONNECT(m_updateNonTunedTimer->timeout, eDVBLocalTimeHandler::updateNonTuned);
}

eDVBLocalTimeHandler::~eDVBLocalTimeHandler()
{
	instance=0;
	// HDSatelit: numai ora sigura ajunge in RTC; o ora provizorie ar fi crezuta sigura la
	// pornirea urmatoare
	if (ready() && hdsceas::sigura(m_hds.stare))
	{
		eDebug("set RTC to previous valid time");
		setRTC(::time(0));
	}
}

void eDVBLocalTimeHandler::readTimeOffsetData( const char* filename )
{
	m_timeOffsetMap.clear();
	FILE *f=fopen(filename, "r");
	if (!f)
		return;
	char line[256];
	if (!fgets(line, 256, f))
	{
		fclose(f);
		return;
	}
	while (true)
	{
		if (!fgets( line, 256, f ))
			break;
		if (strstr(line, "Transponder UTC Time Offsets\n"))
			continue;
		int dvbnamespace,tsid,onid,offs;
		if ( sscanf( line, "%08x,%04x,%04x:%d\n",&dvbnamespace,&tsid,&onid,&offs ) == 4 )
			m_timeOffsetMap[eDVBChannelID(dvbnamespace,tsid,onid)]=offs;
	}
	fclose(f);
}

void eDVBLocalTimeHandler::writeTimeOffsetData( const char* filename )
{
	FILE *f=fopen(filename, "w+");
	if ( f )
	{
		fprintf(f, "Transponder UTC Time Offsets\n");
		for ( std::map<eDVBChannelID,int>::iterator it ( m_timeOffsetMap.begin() ); it != m_timeOffsetMap.end(); ++it )
			fprintf(f, "%08x,%04x,%04x:%d\n",
				it->first.dvbnamespace.get(),
				it->first.transport_stream_id.get(), it->first.original_network_id.get(), it->second );
		fclose(f);
	}
}

void eDVBLocalTimeHandler::setUseDVBTime(bool b)
{
	if (m_use_dvb_time != b) {
		if (m_use_dvb_time) {
			eDebug("[eDVBLocalTimeHandler] disable sync local time with transponder time!");
			std::map<iDVBChannel*, channel_data>::iterator it =
				m_knownChannels.begin();
			for (; it != m_knownChannels.end(); ++it) {
				if (it->second.m_prevChannelState == iDVBChannel::state_ok)
					it->second.tdt = 0;
			}
		}
		else {
			eDebug("[eDVBLocalTimeHandler] enable sync local time with transponder time!");
			std::map<iDVBChannel*, channel_data>::iterator it =
				m_knownChannels.begin();
			for (; it != m_knownChannels.end(); ++it) {
				if (it->second.m_prevChannelState == iDVBChannel::state_ok) {
					it->second.tdt = new TDT(it->second.channel);
					it->second.tdt->start();
				}
			}
		}
		m_use_dvb_time = b;
	}
}

void eDVBLocalTimeHandler::hdsConfirmTime()
{
	// HDSatelit: NTP a pus ceasul (Components/HdsCeas.py): ora devine sigura
	// (Internet), iar ora NTP e noua limita de jos si ancora. Multiplexurile citite pana acum care dau alta ora sunt
	// respinse pentru ceas; corectiile socotite fata de ora de dinainte se uita. Semnalul m_timeUpdated anunta cache-ul
	// EPG (ca la o ora luata din transponder).
	const int inainte = m_hds.stare;
	std::set<hdsceas::Multiplex> respinse;
	m_hds = hdsceas::confirmaInternet(m_hds, time(0), hdsMonoton(), &respinse);
	if (inainte != hdsceas::SIGURA_INTERNET)
		eDebug("[eDVBLocalTimerHandler] ora sigura (Internet), inainte: %s", hdsNumeStare(inainte));
	for (std::set<hdsceas::Multiplex>::const_iterator it = respinse.begin(); it != respinse.end(); ++it)
		eDebug("[eDVBLocalTimerHandler] multiplexul %s respins pentru ceas: alta ora decat Internetul", hdsTextMultiplex(*it).c_str());
	m_timeOffsetMap.clear();
	m_time_ready = true;
	/*emit*/ m_timeUpdated();
}

int eDVBLocalTimeHandler::hdsTimeState() const
{
	return m_hds.stare;
}

bool eDVBLocalTimeHandler::hdsTimeConfirmed() const
{
	return hdsceas::sigura(m_hds.stare);
}

void eDVBLocalTimeHandler::hdsJurnal(const hdsceas::Rezultat &r, hdsceas::Multiplex mux, long long ora_tp, long long acum, int stare_inainte)
{
	// HDSatelit: un rand scurt la fiecare trecere la ora sigura si la fiecare multiplex
	// ignorat (o data pe multiplex si motiv, nu la fiecare TDT)
	const std::string m = hdsTextMultiplex(mux);
	const long long dif = ora_tp - acum;
	switch (r.motiv)
	{
		case hdsceas::DOUA_DE_ACORD:
			eDebug("[eDVBLocalTimerHandler] ora sigura (doua transpondere: %s si %s), inainte: %s, ceasul mutat cu %lld s",
				m.c_str(), hdsTextMultiplex(r.pereche).c_str(), hdsNumeStare(stare_inainte), dif);
			break;
		case hdsceas::PROVIZORIU:
			eDebug("[eDVBLocalTimerHandler] ora provizorie de la multiplexul %s, ceasul mutat cu %lld s", m.c_str(), dif);
			break;
		case hdsceas::INAINTE_DE_CONSTRUIRE:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: ora lui (%s UTC) e inaintea construirii imaginii",
				m.c_str(), hdsTextOra(ora_tp).c_str());
			break;
		case hdsceas::DUPA_LIMITA:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: ora lui (%s UTC) e dupa 2037-12-31",
				m.c_str(), hdsTextOra(ora_tp).c_str());
			break;
		case hdsceas::SUB_LIMITA_DE_JOS:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: ora lui e sub ultima ora sigura (fata de ceas: %lld s)",
				m.c_str(), dif);
			break;
		case hdsceas::RESPINS:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: alte doua multiplexuri sau Internetul au dat alta ora",
				m.c_str());
			break;
		case hdsceas::ASTEAPTA_CONFIRMARE:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: alta ora decat cea %s (fata de ceas: %lld s); astept Internetul sau un al doilea multiplex",
				m.c_str(), hdsceas::sigura(r.nou.stare) ? "sigura" : "provizorie", dif);
			break;
		case hdsceas::MINORITATE:
			eDebug("[eDVBLocalTimerHandler] multiplexul %s ignorat pentru ceas: de acord cu %s (fata de ceas: %lld s), dar mai multe multiplexuri dau ora sigura de acum",
				m.c_str(), hdsTextMultiplex(r.pereche).c_str(), dif);
			break;
		default:
			break;
	}
}

void eDVBLocalTimeHandler::updateNonTuned()
{
	updateTime(-1, 0, 0);
	m_updateNonTunedTimer->start(TIME_UPDATE_INTERVAL, true);
}

void eDVBLocalTimeHandler::updateTime( time_t tp_time, eDVBChannel *chan, int update_count )
{
	int time_difference;
	bool restart_tdt = false;
	if (!tp_time)
		restart_tdt = true;
	else if (tp_time == -1)
	{
		restart_tdt = true;
		/*if ( eSystemInfo::getInstance()->getHwType() == eSystemInfo::DM7020 ||
		( eSystemInfo::getInstance()->getHwType() == eSystemInfo::DM7000
			&& eSystemInfo::getInstance()->hasStandbyWakeupTimer() ) )     TODO !!!!!!! */
		{
			eDebug("[eDVBLocalTimerHandler] no transponder tuned... or no TDT/TOT avail .. try to use RTC :)");
			time_t rtc_time = getRTC();
			// HDSatelit: ceasul se pune din RTC numai cand RTC-ul e sursa orei sigure (crezut la
			// pornire si nemutat de NTP sau de doua transpondere); altfel ar putea duce ceasul la o ora veche
			if (rtc_time && m_hds.stare != hdsceas::SIGURA_RTC)
				eDebug("[eDVBLocalTimerHandler] RTC nefolosit: ora e %s", hdsNumeStare(m_hds.stare));
			else if ( rtc_time ) // RTC Ready?
			{
				tm now;
				localtime_r(&rtc_time, &now);
				eDebug("[eDVBLocalTimerHandler] RTC time is %02d:%02d:%02d",
					now.tm_hour,
					now.tm_min,
					now.tm_sec);
				time_t linuxTime=time(0);
				localtime_r(&linuxTime, &now);
				eDebug("[eDVBLocalTimerHandler] Receiver time is %02d:%02d:%02d",
					now.tm_hour,
					now.tm_min,
					now.tm_sec);
				time_difference = rtc_time - linuxTime;
				eDebug("[eDVBLocalTimerHandler] RTC to Receiver time difference is %ld seconds", linuxTime - rtc_time );
				if ( time_difference )
				{
					eDebug("[eDVBLocalTimerHandler] set Linux Time to RTC Time");
					timeval tnow;
					gettimeofday(&tnow,0);
					tnow.tv_sec=rtc_time;
					settimeofday(&tnow,0);
				}
				else if ( !time_difference )
					eDebug("[eDVBLocalTimerHandler] no change needed");
				else
					eDebug("[eDVBLocalTimerHandler] set to RTC time");
				/*emit*/ m_timeUpdated();
			}
			else
				eDebug("[eDVBLocalTimerHandler] shit RTC not ready :(");
		}
	}
	else
	{
		// HDSatelit: hotararea o ia hdsceas::decide (sus, fara efecte),
		// aici numai se face. Ramurile vechi („ora gata”: corectii pe transponder; „ora negata”: primul transponder crezut
		// bun) sunt inlocuite: ora de la un singur multiplex e provizorie, doua multiplexuri de acord (sau NTP, sau RTC) o
		// fac sigura, iar dupa aceea un singur multiplex o muta cel mult 120 s.
		const eDVBChannelID id = chan->getChannelID();
		const hdsceas::Multiplex mux = hdsMultiplex(id);

 // current linux time
		time_t linuxTime = time(0);

	// difference between current enigma time and transponder time
		int enigma_diff = tp_time-linuxTime;

		bool updated = m_time_ready;

		const int stare_inainte = m_hds.stare;
		hdsceas::Rezultat r = hdsceas::decide(m_hds, mux, tp_time, hdsMonoton(), linuxTime);
		m_hds = r.nou;
		if (r.jurnal)
			hdsJurnal(r, mux, tp_time, linuxTime, stare_inainte);
		if (!r.muta)
		{
			// ceasul ramane; corectia acestui transponder se tine minte, ca in enigma2 de baza
			m_timeOffsetMap[id] = -enigma_diff;
			m_last_tp_time_difference = enigma_diff;
			return;
		}
		if (r.motiv != hdsceas::POTRIVIRE)
			m_timeOffsetMap.clear(); // ceasul trece pe o ora noua: corectiile socotite fata de cea veche nu mai au sens
		m_timeOffsetMap[id] = 0;
		if (m_hds.stare != stare_inainte)
			updated = false; // starea s-a schimbat: m_timeUpdated se trimite si fara mutare (EPG, Components/HdsCeas.py)
		m_time_ready = true;

		time_t t = (time_t)r.ora;
		int new_diff = (int)(t - linuxTime);
		m_last_tp_time_difference=tp_time-t;

		if (!new_diff &&
			updated) // overrride this check on first received TDT
		{
			eDebug("[eDVBLocalTimerHandler] not changed");
			return;
		}

		// HDSatelit: numai ora sigura ajunge in RTC (o ora provizorie ar fi crezuta sigura la
		// pornirea urmatoare), iar ora RTC o inlocuieste pe cea din transponder numai cand RTC-ul e sursa orei sigure
		if ( !update_count )
		{
			// set rtc to calced transponder time when the first tdt is received on this
			// transponder
			if (hdsceas::sigura(m_hds.stare))
			{
				setRTC(t);
				eDebug("[eDVBLocalTimerHandler] update RTC");
			}
		}
		else if (m_hds.stare == hdsceas::SIGURA_RTC && getRTC())
		{
			if (abs(getRTC() - t) > 60)
			{
				eDebug("[eDVBLocalTimerHandler] difference between new linux time and RTC time is > 60 sec... transponder time looks not ok... use rtc time");
				t = getRTC();
			}
			else
				eDebug("[eDVBLocalTimerHandler] difference between linux time and RTC time is < 60 sec... so the transponder time looks ok");
		}
		else
			eDebug("[eDVBLocalTimerHandler] no RTC available :(");

		tm now;
		localtime_r(&t, &now);
		eDebug("[eDVBLocalTimerHandler] time update to %02d:%02d:%02d",
			now.tm_hour,
			now.tm_min,
			now.tm_sec);

		time_difference = t - linuxTime;   // calc our new linux_time -> enigma_time correction
		eDebug("[eDVBLocalTimerHandler] m_time_difference is %d", time_difference );

		if ( time_difference )
		{
			eDebug("[eDVBLocalTimerHandler] set Linux Time");
			timeval tnow;
			gettimeofday(&tnow,0);
			tnow.tv_sec=t;
			settimeofday(&tnow,0);
		}

 		 /*emit*/ m_timeUpdated();
	}

	if ( restart_tdt )
	{
		std::map<iDVBChannel*, channel_data>::iterator it =
			m_knownChannels.find(chan);
		if ( it != m_knownChannels.end() )
		{
			int updateCount = it->second.tdt->getUpdateCount();
			it->second.tdt = 0;
			it->second.tdt = new TDT(chan, updateCount);
			it->second.tdt->startTimer(TIME_UPDATE_INTERVAL);  // restart TDT for this transponder in 30min
		}
	}
}

void eDVBLocalTimeHandler::DVBChannelAdded(eDVBChannel *chan)
{
	if ( chan )
	{
//		eDebug("[eDVBLocalTimerHandler] add channel %p", chan);
		std::pair<std::map<iDVBChannel*, channel_data>::iterator, bool> tmp =
			m_knownChannels.insert( std::pair<iDVBChannel*, channel_data>(chan, channel_data()) );
		tmp.first->second.tdt = NULL;
		tmp.first->second.channel = chan;
		tmp.first->second.m_prevChannelState = -1;
		chan->connectStateChange(sigc::mem_fun(*this, &eDVBLocalTimeHandler::DVBChannelStateChanged), tmp.first->second.m_stateChangedConn);
	}
}

void eDVBLocalTimeHandler::DVBChannelStateChanged(iDVBChannel *chan)
{
	std::map<iDVBChannel*, channel_data>::iterator it =
		m_knownChannels.find(chan);
	if ( it != m_knownChannels.end() )
	{
		int state=0;
		chan->getState(state);
		if ( state != it->second.m_prevChannelState )
		{
			switch (state)
			{
				case iDVBChannel::state_ok:
					eDebug("[eDVBLocalTimerHandler] channel %p running", chan);
					m_updateNonTunedTimer->stop();
					if (m_use_dvb_time) {
						it->second.tdt = new TDT(it->second.channel);
						it->second.tdt->start();
					}
					break;
				case iDVBChannel::state_release:
					eDebug("[eDVBLocalTimerHandler] remove channel %p", chan);
					m_knownChannels.erase(it);
					if (m_knownChannels.empty())
						m_updateNonTunedTimer->start(TIME_UPDATE_INTERVAL, true);
					break;
				default: // ignore all other events
					return;
			}
			it->second.m_prevChannelState = state;
		}
	}
}
