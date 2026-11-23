/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_dvb_hdsepgpoarta_h
#define __lib_dvb_hdsepgpoarta_h

/*
 * HDSatelit 0.7.8: poarta importatorilor ghidului (eEPGCache::importEvents, din firele Python ale importului IPTV si
 * XMLTV) fata de distrugerea cache-ului la iesirea interfetei.
 *
 * La iesire, ~eMain elibereaza ultimul ePtr al lui eEPGCache, deci ~eEPGCache ruleaza pe firul principal, cu GIL-ul
 * tinut. Un fir Python care importa ghidul tine numai pointerul dat de eEPGCache.getInstance() (fara referinta): daca e
 * in importEvents, cu GIL-ul lasat (Py_BEGIN_ALLOW_THREADS), sau intra acolo mai tarziu, in Py_Finalize (functiile
 * atexit lasa GIL-ul si altor fire), scrie in eventDB-ul unui obiect distrus. Asa cadea enigma2 la iesire cu semnalul
 * 11 in unordered_map<uniqueEPGKey>::operator[] chemat din importIptvRows (0.7.6 si 0.7.7, dupa "reached rl -1").
 *
 * Poarta e statica (traieste cat procesul, nu cat obiectul) si nu tine niciun lacat:
 *  - importatorul se numara INAINTE sa citeasca poarta (Import), iar inchiderea pune poarta INAINTE sa citeasca
 *    numaratoarea (inchide); cu ordinea secventiala a atomicelor, un importator care a gasit poarta deschisa e
 *    numarat cand inchiderea citeste, deci distrugerea il asteapta;
 *  - importatorul iese din numaratoare inainte sa ceara GIL-ul inapoi (destructorul, care il asteapta, tine GIL-ul);
 *  - inchiderea asteapta cel mult `pasi` x 10 ms; dupa kill, destructorul ia import_lock inainte sa elibereze membrii;
 *    fiecare citire a membrilor din blocul fara GIL ia acelasi lacat static si verifica din nou poarta. Astfel un fir
 *    oprit mai mult decat termenul nu poate citi obiectul eliberat cand revine;
 *  - import_lock nu se tine cat se asteapta: ultima salvare a ghidului, pe firul EPG, il ia si ea.
 * Un importator care gaseste poarta inchisa intoarce 0 (nimic importat) fara sa atinga obiectul.
 */

#include <atomic>
#include <chrono>
#include <thread>

namespace hdsepg
{

inline std::atomic<bool> &inchisa()
{
	static std::atomic<bool> v(false);
	return v;
}

inline std::atomic<int> &inLucru()
{
	static std::atomic<int> v(0);
	return v;
}

/* cat traieste obiectul, importatorul e numarat; deschisa() spune daca are voie sa atinga cache-ul */
class Import
{
public:
	Import(): m_deschisa(false)
	{
		inLucru().fetch_add(1);
		m_deschisa = !inchisa().load();
	}
	~Import()
	{
		inLucru().fetch_sub(1);
	}
	bool deschisa() const { return m_deschisa; }
private:
	bool m_deschisa;
	Import(const Import &);
	Import &operator=(const Import &);
};

inline bool eInchisa()
{
	return inchisa().load();
}

/* ~eEPGCache: nimeni nu mai intra; asteapta importatorii intrati, cel mult pasi x 10 ms. Intoarce cati au ramas. */
inline int inchide(int pasi = 500)
{
	inchisa().store(true);
	int ramasi = inLucru().load();
	for (int i = 0; ramasi > 0 && i < pasi; ++i)
	{
		std::this_thread::sleep_for(std::chrono::milliseconds(10));
		ramasi = inLucru().load();
	}
	return ramasi;
}

}

#endif
