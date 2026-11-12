/* SoftCSA (software descrambling of CSA-ALT with libdvbcsa). GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvbcsaengine_h
#define __dvbcsaengine_h

#include <lib/base/object.h>
#include <vector>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <stdint.h>
#include <stddef.h>
#include <string>

// Forward declarations for libdvbcsa
struct dvbcsa_bs_key_s;
typedef struct dvbcsa_bs_key_s dvbcsa_bs_key_t;

struct dvbcsa_bs_batch_s {
	unsigned char *data;
	unsigned int len;
};
typedef struct dvbcsa_bs_batch_s dvbcsa_bs_batch_s;

// Function pointer types for dlopen API
typedef dvbcsa_bs_key_t *(*dvbcsa_bs_key_alloc_f)(void);
typedef void (*dvbcsa_bs_key_free_f)(dvbcsa_bs_key_t *);
typedef void (*dvbcsa_bs_key_set_ecm_f)(uint8_t ecm_mode, const uint8_t *cw, dvbcsa_bs_key_t *);
typedef unsigned char (*dvbcsa_get_ecm_table_f)(void);
typedef size_t (*dvbcsa_bs_batch_size_f)(void);
typedef void (*dvbcsa_bs_decrypt_f)(const dvbcsa_bs_key_t *key, dvbcsa_bs_batch_s *pcks, int maxlen);

// Global dlopen API structure
struct csa_dlopen_api
{
	void *handle;
	bool tried;
	bool available;
	dvbcsa_bs_key_alloc_f    key_alloc;
	dvbcsa_bs_key_free_f     key_free;
	dvbcsa_bs_key_set_ecm_f  key_set_ecm;
	dvbcsa_get_ecm_table_f   get_ecm_table;
	dvbcsa_bs_batch_size_f   batch_size;
	dvbcsa_bs_decrypt_f      decrypt;
};

// Global API instance (defined in csaengine.cpp)
extern csa_dlopen_api g_csa_api;

// Load libdvbcsa dynamically (call once at startup)
bool csa_load_library();

// HDSatelit: counters of all engines, for the proofs and the state shown in Python (hdsSoftCsaStare): packets given to
// libdvbcsa, packets turned into null packets (no key yet), keys set. Added once per descramble() call.
struct csa_counters
{
	std::atomic<unsigned long long> descrambled{0};
	std::atomic<unsigned long long> nulled{0};
	std::atomic<unsigned long long> keys{0};
	// HDSatelit 0.7.4: the parity changes seen in the stream, those whose key was not the new one yet (the control word
	// came after the change), the waits for it (count, ms in total, the longest, those that ran out of time)
	std::atomic<unsigned long long> flips{0};
	std::atomic<unsigned long long> late{0};
	std::atomic<unsigned long long> waits{0};
	std::atomic<unsigned long long> wait_ms{0};
	std::atomic<unsigned long long> wait_max_ms{0};
	std::atomic<unsigned long long> wait_expired{0};
	// a wait in progress now and the monotonic ms when the last one ended: the health check of the loop
	// (eDVBSoftDecoder::streamHealthCheck) does not take that pause of the picture for a hung decoder
	std::atomic<int> waiting_now{0};
	std::atomic<long long> wait_end_ms{0};
	/* HDSatelit 0.7.4: the key of every new period checked on its first packet with a PES start (the
	   descrambled payload must begin with 00 00 01) and those that did not work: a softcam line that answers in time but
	   with a wrong control word freezes the picture for a whole period (7 s on Sky DE) and looked like a healthy system */
	std::atomic<unsigned long long> key_checks{0};
	std::atomic<unsigned long long> bad_keys{0};
	/* the verdicts on those keys sent to the softcam (DVBAPI_HDS_CW_REPORT) and those lost (no softcam that asked for
	   them, or the queue full) */
	std::atomic<unsigned long long> verdicts_sent{0};
	std::atomic<unsigned long long> verdicts_lost{0};
};
extern csa_counters g_csa_counters;

/* HDSatelit 0.7.4: the verdict on the key of every new period (checkKey: the control word half, its parity, whether it
   descrambled the first PES start) given to whoever listens: eDVBCAHandler sends it to a softcam that announced
   "hdsk1", which pauses on that channel the line that gave a wrong word. Called on the recorder thread: it must not
   block. Null when nobody listens. */
typedef void (*csa_key_verdict_fn)(const uint8_t *cw, int parity, bool works);
extern std::atomic<csa_key_verdict_fn> g_csa_key_verdict;

/**
 * eDVBCSAEngine - Low-Level CSA Descrambler
 *
 * Thread-safe wrapper around libdvbcsa using double-buffered keys.
 * setKey() from CWHandler thread and descramble() from recorder thread
 * can run concurrently without locks.
 *
 * Each parity (even/odd) has two key slots. setKey() writes into the
 * inactive slot, then atomically swaps the active index. descramble()
 * snapshots the active index once per call and uses it throughout.
 */
class eDVBCSAEngine
{
	DECLARE_REF(eDVBCSAEngine);

public:
	eDVBCSAEngine();
	~eDVBCSAEngine();

	// Initialization
	bool init();

	// Static helpers
	static bool isAvailable() { csa_load_library(); return g_csa_api.available; }
	static int getBatchSize();
	static std::string getLibraryName();
	static std::string getLibraryPath();
	static std::string getLibraryVersion();

	// Key Management (thread-safe, called from CWHandler thread)
	void setKey(int parity, uint8_t ecm_mode, const uint8_t* cw);
	void clearKeys();

	// Descrambling (called from recorder thread)
	void descramble(unsigned char* packets, int len);

	/* HDSatelit 0.7.4: the wait for the new key at a parity change. When the stream changes to the other parity and the
	   key of that parity is still the one of its previous period (the control word comes later than the change: on
	   Sky DE ICAM every answer of the softcam slower than about 620 ms, measured on Octagon SF8008 11.11.2026), the
	   packets are held (the recorder thread waits, at most HOLD_MAX_MS) until the key comes, instead of giving the
	   decoder packets it cannot decode (a stop of 1-2 s and a jump forward). A key reused for the next period is
	   recognized: a packet with a PES start, descrambled on a copy with the key there is, must begin with 00 00 01.
	   Off by default: only the loop of the live service arms it (armHolds when the loop starts, its demux buffer is 6 MiB);
	   the engines of recordings and of the timeshift recorder keep their 1 MiB and no wait (stopping them does not wait).
	   releaseHolds (main thread, before the loop stops) ends a wait at once and allows no new one. */
	enum { HOLD_MAX_MS = 2000, SAME_BOUNDARY_MS = 1000 };
	void releaseHolds();
	void armHolds();

	// Status
	bool hasEvenKey() const { return m_key_even_set; }
	bool hasOddKey() const { return m_key_odd_set; }
	bool hasAnyKey() const { return hasEvenKey() || hasOddKey(); }
	int getBatchSizeInstance() const { return m_batch_size; }

private:
	// Double-buffered keys: two slots per parity, atomic index selects active one.
	// setKey() writes to inactive slot, then swaps index.
	// descramble() reads active slot via snapshot of index.
	dvbcsa_bs_key_t* m_key_even[2];
	dvbcsa_bs_key_t* m_key_odd[2];
	std::atomic<int> m_key_even_idx{0};    // active index for even key (0 or 1)
	std::atomic<int> m_key_odd_idx{0};     // active index for odd key (0 or 1)
	std::atomic<bool> m_key_even_set{false};
	std::atomic<bool> m_key_odd_set{false};
	int m_batch_size;
	unsigned int m_bad_packets{0};  // Log rate limit only, races are harmless

	// HDSatelit 0.7.4: the wait for the new key (descramble(), releaseHolds())
	std::mutex m_hold_mutex;
	std::condition_variable m_hold_cv;
	std::atomic<bool> m_holds_on{false};          // only the loop of the live service arms it (servicedvb.cpp)
	std::atomic<unsigned> m_key_gen[2];          // bumped by setKey only when the control word of the parity changes
	std::atomic<long long> m_key_changed_ms[2];  // monotonic ms of that change
	uint8_t m_last_cw[2][8];                     // setKey thread only
	uint8_t m_slot_cw[2][2][8];                  // the control word of each key slot [parity][slot], written before the
	                                             // slot is published (read by checkKey for the verdict)
	bool m_last_cw_set[2];
	int m_parity{-1};                            // recorder thread only: the parity of the last scrambled packet
	unsigned m_gen_at_end[2];                    // recorder thread only: m_key_gen when that parity last ended
	long long m_seen_ms[2];                      // recorder thread only: the last descramble() with packets of that parity
	void noteFlip(int parity, unsigned gen, long long lead, int works, long long held);
	static long long nowMs();
	// 1: the key works on the first packet of the parity with a PES start, 0: it does not, -1: no such packet there
	int keyWorks(int parity, const dvbcsa_bs_key_t* key, const unsigned char* packets, int from, int len);
	// the key of the period begun at the last change of this parity is still to be checked (recorder thread only)
	bool m_check_pending[2] = {false, false};
	void checkKey(int parity, const dvbcsa_bs_key_t* key, const unsigned char* packets, int at);
	void waitForKey(int parity, unsigned gen_old);

	// Pre-allocated batch arrays
	std::vector<dvbcsa_bs_batch_s> m_batch_even;
	std::vector<dvbcsa_bs_batch_s> m_batch_odd;

	// TS Packet Helpers
	static bool isPacketValid(const unsigned char* pkt);
	static unsigned char getScrambledBits(const unsigned char* pkt);
	static int getPayloadOffset(const unsigned char* pkt);
	static void clearTSC(unsigned char* pkt);
	static void setNullPacket(unsigned char* pkt);
	void logBadPacket(const char* reason, const unsigned char* pkt, int offset, int len);
};

#endif // __dvbcsaengine_h
