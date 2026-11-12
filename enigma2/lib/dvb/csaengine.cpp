/* SoftCSA (software descrambling of CSA-ALT with libdvbcsa). GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/dvb/csaengine.h>
#include <lib/base/eerror.h>
#include <dlfcn.h>
#include <climits>
#include <chrono>
#include <time.h>
#include <stdio.h>
#include <sys/stat.h>
#include <cstdlib>
#include <cstring>
#include <string>

#define CSA_DEBUG 0
#if CSA_DEBUG
#define CSA_LOG(...) eDebug(__VA_ARGS__)
#else
#define CSA_LOG(...) do {} while (0)
#endif

#define BYTE_HEX(b) ((unsigned int)(b) & 0xFF)

DEFINE_REF(eDVBCSAEngine);

csa_counters g_csa_counters;
std::atomic<csa_key_verdict_fn> g_csa_key_verdict{nullptr};

// Global API object
csa_dlopen_api g_csa_api = {
	0,      // handle
	false,  // tried
	false,  // available
	0, 0, 0, 0, 0
};

bool csa_load_library()
{
	// Already loaded successfully?
	if (g_csa_api.available)
		return true;

	// Already tried and failed?
	if (g_csa_api.tried)
		return false;

	g_csa_api.tried = true;

	const char *candidates[] = {
		"libdvbcsa.so.1",
		"libdvbcsa.so",
		0
	};

	const char *loaded_name = nullptr;

	for (int i = 0; candidates[i]; ++i)
	{
		g_csa_api.handle = dlopen(candidates[i], RTLD_NOW | RTLD_LOCAL);
		if (g_csa_api.handle)
		{
			loaded_name = candidates[i];
			break;
		}
	}

	if (!g_csa_api.handle)
	{
		eDebug("[eDVBCSAEngine] libdvbcsa not found, software CSA is disabled");
		return false;
	}

	// Resolve symbols
	g_csa_api.key_alloc   = (dvbcsa_bs_key_alloc_f)  dlsym(g_csa_api.handle, "dvbcsa_bs_key_alloc");
	g_csa_api.key_free    = (dvbcsa_bs_key_free_f)   dlsym(g_csa_api.handle, "dvbcsa_bs_key_free");
	g_csa_api.key_set_ecm = (dvbcsa_bs_key_set_ecm_f)dlsym(g_csa_api.handle, "dvbcsa_bs_key_set_ecm");
	g_csa_api.get_ecm_table = (dvbcsa_get_ecm_table_f)dlsym(g_csa_api.handle, "dvbcsa_get_ecm_table");
	g_csa_api.batch_size  = (dvbcsa_bs_batch_size_f) dlsym(g_csa_api.handle, "dvbcsa_bs_batch_size");
	g_csa_api.decrypt     = (dvbcsa_bs_decrypt_f)    dlsym(g_csa_api.handle, "dvbcsa_bs_decrypt");

	if (!g_csa_api.key_alloc   ||
		!g_csa_api.key_free    ||
		!g_csa_api.key_set_ecm ||
		!g_csa_api.batch_size  ||
		!g_csa_api.decrypt)
	{
		eWarning("[eDVBCSAEngine] %s loaded but missing required symbols, software CSA is disabled", loaded_name);
		dlclose(g_csa_api.handle);
		g_csa_api.handle    = 0;
		g_csa_api.available = false;
		return false;
	}

	g_csa_api.available = true;

	eDebug("[eDVBCSAEngine] %s successfully loaded, software CSA enabled", loaded_name);

	return true;
}

eDVBCSAEngine::eDVBCSAEngine()
	: m_key_even{nullptr, nullptr}
	, m_key_odd{nullptr, nullptr}
	, m_batch_size(0)
{
	for (int p = 0; p < 2; ++p)
	{
		m_key_gen[p].store(0, std::memory_order_relaxed);
		m_key_changed_ms[p].store(0, std::memory_order_relaxed);
		memset(m_last_cw[p], 0, sizeof(m_last_cw[p]));
		memset(m_slot_cw[p], 0, sizeof(m_slot_cw[p]));
		m_last_cw_set[p] = false;
		m_gen_at_end[p] = 0;
		m_seen_ms[p] = 0;
	}
}

/* HDSatelit 0.7.4: one line per parity change in /tmp/hds-softcsa-paritate.log (recorder thread, every few seconds; the
   debug lines of this thread do not reach the interface log): monotonic ms, the new parity, the key generation and the
   one at the end of its previous period, how long before the change its key came (negative: after), whether it worked
   on a PES start (1, 0, -1 not tried) and how long the packets waited. Kept under 64 KiB (the file starts again). */
void eDVBCSAEngine::noteFlip(int parity, unsigned gen, long long lead, int works, long long held)
{
	const char *cale = "/tmp/hds-softcsa-paritate.log";
	struct stat st;
	const char *mod = (::stat(cale, &st) == 0 && st.st_size > 64 * 1024) ? "w" : "a";
	FILE *f = fopen(cale, mod);
	if (!f)
		return;
	fprintf(f, "%lld p=%d gen=%u sfarsit=%u inainte_ms=%lld merge=%d asteptat_ms=%lld\n", nowMs(), parity, gen,
		m_gen_at_end[parity], lead, works, held);
	fclose(f);
}

long long eDVBCSAEngine::nowMs()
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

void eDVBCSAEngine::releaseHolds()
{
	m_holds_on.store(false, std::memory_order_release);
	{
		std::lock_guard<std::mutex> l(m_hold_mutex);
	}
	m_hold_cv.notify_all();
}

void eDVBCSAEngine::armHolds()
{
	m_holds_on.store(true, std::memory_order_release);
}

/* HDSatelit 0.7.4: the first packet of this parity with a PES start (from `from` on), descrambled on a copy with `key`:
   1 when it begins with 00 00 01 (the key there is the right one), 0 when it does not, -1 when there is no such packet
   in the buffer (told apart, so a buffer without a PES start is not counted as a wrong key) */
int eDVBCSAEngine::keyWorks(int parity, const dvbcsa_bs_key_t* key, const unsigned char* packets, int from, int len)
{
	for (int j = from; j + 188 <= len; j += 188)
	{
		const unsigned char* pkt = packets + j;
		if (!isPacketValid(pkt))
			return -1;
		const unsigned char sc = getScrambledBits(pkt);
		if (sc < 2 || (sc == 2 ? 0 : 1) != parity || !(pkt[1] & 0x40) || !(pkt[3] & 0x10))
			continue;
		const int offset = getPayloadOffset(pkt);
		if (offset > 185)
			continue;
		unsigned char copy[188];
		memcpy(copy, pkt, 188);
		dvbcsa_bs_batch_s batch[2];
		batch[0].data = copy + offset;
		batch[0].len = 188 - offset;
		batch[1].data = NULL;
		batch[1].len = 0;
		g_csa_api.decrypt(key, batch, 184);
		return (copy[offset] == 0 && copy[offset + 1] == 0 && copy[offset + 2] == 1) ? 1 : 0;
	}
	return -1;
}

/* HDSatelit 0.7.4: the check of the key of a new period, on the first packet of the parity with a PES start (the packet at
   `at`, before it is descrambled in place). Octagon SF8008 on Sky DE ICAM: some lines of the softcam
   answered in time ("found" in 450 ms) with control words that do not descramble; every answer of such a line froze the
   picture for one whole period (6.5 s, 13.5 s for two) and nothing showed why. A wrong key is counted (bad_keys, the
   chei_gresite line of /tmp/hds-softcsa.stat) and written in the parity log. Only counted: there is no better key to take. */
void eDVBCSAEngine::checkKey(int parity, const dvbcsa_bs_key_t* key, const unsigned char* packets, int at)
{
	const int works = keyWorks(parity, key, packets, at, at + 188);
	if (works < 0)
		return;  // not a PES start with payload: the next packet of the parity is tried
	m_check_pending[parity] = false;
	g_csa_counters.key_checks.fetch_add(1, std::memory_order_relaxed);
	/* the verdict to the softcam, with the control word of the slot this key came from (the line is found by the word) */
	csa_key_verdict_fn verdict = g_csa_key_verdict.load(std::memory_order_acquire);
	if (verdict)
	{
		dvbcsa_bs_key_t* const* slots = parity ? m_key_odd : m_key_even;
		const int slot = key == slots[1] ? 1 : 0;
		uint8_t cw[8];
		memcpy(cw, m_slot_cw[parity][slot], 8);
		verdict(cw, parity, works == 1);
	}
	if (works)
		return;
	g_csa_counters.bad_keys.fetch_add(1, std::memory_order_relaxed);
	const char *cale = "/tmp/hds-softcsa-paritate.log";
	struct stat st;
	const char *mod = (::stat(cale, &st) == 0 && st.st_size > 64 * 1024) ? "w" : "a";
	FILE *f = fopen(cale, mod);
	if (!f)
		return;
	fprintf(f, "%lld p=%d cheie_gresita gen=%u\n", nowMs(), parity, m_key_gen[parity].load(std::memory_order_relaxed));
	fclose(f);
}

void eDVBCSAEngine::waitForKey(int parity, unsigned gen_old)
{
	const long long t0 = nowMs();
	bool came;
	g_csa_counters.waiting_now.fetch_add(1, std::memory_order_relaxed);
	{
		std::unique_lock<std::mutex> l(m_hold_mutex);
		came = m_hold_cv.wait_for(l, std::chrono::milliseconds(HOLD_MAX_MS), [&] {
			return !m_holds_on.load(std::memory_order_acquire) ||
				m_key_gen[parity].load(std::memory_order_acquire) != gen_old; // S8417: pairs with setKey
		});
	}
	const unsigned long long ms = (unsigned long long)(nowMs() - t0);
	g_csa_counters.wait_end_ms.store(nowMs(), std::memory_order_relaxed);
	g_csa_counters.waiting_now.fetch_sub(1, std::memory_order_relaxed);
	g_csa_counters.waits.fetch_add(1, std::memory_order_relaxed);
	g_csa_counters.wait_ms.fetch_add(ms, std::memory_order_relaxed);
	unsigned long long max = g_csa_counters.wait_max_ms.load(std::memory_order_relaxed);
	while (ms > max && !g_csa_counters.wait_max_ms.compare_exchange_weak(max, ms, std::memory_order_relaxed))
		;
	if (!came)
		g_csa_counters.wait_expired.fetch_add(1, std::memory_order_relaxed);
	eDebug("[eDVBCSAEngine] %s parity: the key came after the change, packets held %llu ms%s", parity ? "odd" : "even", ms,
		came ? "" : " (no key in time, the old one is used)");
}

eDVBCSAEngine::~eDVBCSAEngine()
{
	if (g_csa_api.available && g_csa_api.key_free)
	{
		for (int i = 0; i < 2; ++i)
		{
			if (m_key_even[i])
			{
				g_csa_api.key_free(m_key_even[i]);
				m_key_even[i] = nullptr;
			}
			if (m_key_odd[i])
			{
				g_csa_api.key_free(m_key_odd[i]);
				m_key_odd[i] = nullptr;
			}
		}
	}
}

bool eDVBCSAEngine::init()
{
	if (!csa_load_library())
	{
		eWarning("[eDVBCSAEngine] init: csa_load_library failed");
		return false;
	}

	m_batch_size = g_csa_api.batch_size();

	for (int i = 0; i < 2; ++i)
	{
		m_key_even[i] = g_csa_api.key_alloc();
		m_key_odd[i] = g_csa_api.key_alloc();
		if (!m_key_even[i] || !m_key_odd[i])
		{
			eWarning("[eDVBCSAEngine] init: key_alloc failed");
			return false;
		}
	}

	// Pre-allocate batch arrays
	m_batch_even.resize(m_batch_size + 1);
	m_batch_odd.resize(m_batch_size + 1);

	eDebug("[eDVBCSAEngine] init: batch_size=%d", m_batch_size);

	return true;
}

int eDVBCSAEngine::getBatchSize()
{
	if (!g_csa_api.available || !g_csa_api.batch_size)
		return 0;
	return g_csa_api.batch_size();
}

std::string eDVBCSAEngine::getLibraryName()
{
	std::string path = getLibraryPath();
	if (path.empty())
		return "";

	// Extract filename from path
	size_t lastSlash = path.rfind('/');
	std::string filename = (lastSlash != std::string::npos) ? path.substr(lastSlash + 1) : path;

	// Remove everything from ".so"
	size_t soPos = filename.find(".so");
	if (soPos != std::string::npos)
	{
		return filename.substr(0, soPos);
	}

	return filename;
}

std::string eDVBCSAEngine::getLibraryPath()
{
	if (!g_csa_api.available || !g_csa_api.handle)
		return "";

	// Use dladdr to get the path of a symbol from the library
	Dl_info info;
	if (dladdr((void*)g_csa_api.key_alloc, &info) && info.dli_fname)
		return info.dli_fname;

	return "";
}

std::string eDVBCSAEngine::getLibraryVersion()
{
	std::string path = getLibraryPath();
	if (path.empty())
		return "";

	char resolved[PATH_MAX];
	if (!realpath(path.c_str(), resolved))
		return "";

	std::string full(resolved);
	std::string marker = ".so.";
	size_t pos = full.rfind(marker);
	if (pos != std::string::npos)
	{
		return full.substr(pos + marker.length());
	}

	return "";
}

void eDVBCSAEngine::setKey(int parity, uint8_t ecm_mode, const uint8_t* cw)
{
	if (!cw)
		return;
	if (!m_key_even[0] || !m_key_even[1] || !m_key_odd[0] || !m_key_odd[1])
		return;
	if (!g_csa_api.available || !g_csa_api.key_set_ecm)
		return;

	CSA_LOG("[eDVBCSAEngine] setKey: parity=%d ecm_mode=%u CW=%02X %02X %02X %02X %02X %02X %02X %02X",
			parity, ecm_mode,
			BYTE_HEX(cw[0]), BYTE_HEX(cw[1]), BYTE_HEX(cw[2]), BYTE_HEX(cw[3]),
			BYTE_HEX(cw[4]), BYTE_HEX(cw[5]), BYTE_HEX(cw[6]), BYTE_HEX(cw[7]));

	// Double-buffered key update: write to inactive slot, then swap index.
	// descramble() on the recorder thread reads the active slot via atomic index,
	// so it never sees a partially-written key schedule.
	if (parity == 0) // even
	{
		int active = m_key_even_idx.load(std::memory_order_relaxed); // S8417: only this thread writes it
		int inactive = 1 - active;
		g_csa_api.key_set_ecm(ecm_mode, cw, m_key_even[inactive]);
		memcpy(m_slot_cw[0][inactive], cw, 8);  // published with the index below
		m_key_even_idx.store(inactive, std::memory_order_release); // S8417: publishes key write above
		m_key_even_set.store(true, std::memory_order_release); // S8417: publishes idx store above
	}
	else // odd
	{
		int active = m_key_odd_idx.load(std::memory_order_relaxed); // S8417: only this thread writes it
		int inactive = 1 - active;
		g_csa_api.key_set_ecm(ecm_mode, cw, m_key_odd[inactive]);
		memcpy(m_slot_cw[1][inactive], cw, 8);  // published with the index below
		m_key_odd_idx.store(inactive, std::memory_order_release); // S8417: publishes key write above
		m_key_odd_set.store(true, std::memory_order_release); // S8417: publishes idx store above
	}
	g_csa_counters.keys.fetch_add(1, std::memory_order_relaxed);

	// HDSatelit 0.7.4: a new control word for this parity (not the same one sent again) ends a wait for it in descramble()
	const int p = parity == 0 ? 0 : 1;
	if (!m_last_cw_set[p] || memcmp(m_last_cw[p], cw, 8))
	{
		memcpy(m_last_cw[p], cw, 8);
		m_last_cw_set[p] = true;
		m_key_changed_ms[p].store(nowMs(), std::memory_order_relaxed);
		m_key_gen[p].fetch_add(1, std::memory_order_release); // S8417: after the key slot swap above
		{
			std::lock_guard<std::mutex> l(m_hold_mutex);
		}
		m_hold_cv.notify_all();
	}

	if (g_csa_api.get_ecm_table)
	{
		static uint8_t last_logged_table = 0xFF;
		uint8_t table_used = g_csa_api.get_ecm_table();
		if (table_used != last_logged_table)
		{
			eDebug("[eDVBCSAEngine] libdvbcsa using table 0x%02X", table_used);
			last_logged_table = table_used;
		}
	}
}

void eDVBCSAEngine::clearKeys()
{
	m_key_even_set = false;
	m_key_odd_set = false;
}

// TS Packet Helpers
bool eDVBCSAEngine::isPacketValid(const unsigned char* pkt)
{
	return pkt[0] == 0x47;
}

unsigned char eDVBCSAEngine::getScrambledBits(const unsigned char* pkt)
{
	return pkt[3] >> 6;
}

int eDVBCSAEngine::getPayloadOffset(const unsigned char* pkt)
{
	unsigned char adapt_field = (pkt[3] & ~0xDF) >> 5;

	if (adapt_field)
		return 4 + 1 + pkt[4];    // header (4) + length byte + adaptation field
	else
		return 4;                 // header only
}

void eDVBCSAEngine::clearTSC(unsigned char* pkt)
{
	if (pkt)
		pkt[3] &= 0x3F;
}

void eDVBCSAEngine::setNullPacket(unsigned char* pkt)
{
	// PID 0x1FFF, the decoder ignores null packets
	clearTSC(pkt);
	pkt[1] = 0x1F;
	pkt[2] = 0xFF;
}

void eDVBCSAEngine::logBadPacket(const char* reason, const unsigned char* pkt, int offset, int len)
{
	++m_bad_packets;
	if (m_bad_packets > 20 && m_bad_packets % 500)
		return;
	if (len - offset >= 5)
		eWarning("[eDVBCSAEngine] bad packet #%u (%s): offset=%d len=%d tei=%d hdr=%02X %02X %02X %02X %02X", m_bad_packets, reason, offset, len,
			(pkt[1] & 0x80) ? 1 : 0, BYTE_HEX(pkt[0]), BYTE_HEX(pkt[1]), BYTE_HEX(pkt[2]), BYTE_HEX(pkt[3]), BYTE_HEX(pkt[4]));
	else
		eWarning("[eDVBCSAEngine] bad packet #%u (%s): offset=%d len=%d", m_bad_packets, reason, offset, len);
}

// Descrambling
void eDVBCSAEngine::descramble(unsigned char* packets, int len)
{
	if (!packets || len <= 0)
		return;
	if (m_batch_size <= 0)
		return;
	if (!g_csa_api.available || !g_csa_api.decrypt)
		return;
	if (m_batch_even.empty() || m_batch_odd.empty())
		return;

	// Snapshot active key state and indices once for this entire buffer.
	// setKey() on the CWHandler thread may swap the index at any time,
	// but we consistently use the snapshot throughout this call.
	bool even_set = m_key_even_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
	bool odd_set = m_key_odd_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
	dvbcsa_bs_key_t* key_even = even_set ? m_key_even[m_key_even_idx.load(std::memory_order_acquire)] : nullptr; // S8417: pairs with release in setKey()
	dvbcsa_bs_key_t* key_odd = odd_set ? m_key_odd[m_key_odd_idx.load(std::memory_order_acquire)] : nullptr; // S8417: pairs with release in setKey()

	int i        = 0;
	int even_cnt = 0;
	int odd_cnt  = 0;
	unsigned int given = 0, nulled = 0; // HDSatelit: g_csa_counters
	bool seen_even = false, seen_odd = false; // HDSatelit 0.7.4: parities in this buffer (m_seen_ms)

	// Use pre-allocated member vectors
	dvbcsa_bs_batch_s* pcks_even = m_batch_even.data();
	dvbcsa_bs_batch_s* pcks_odd = m_batch_odd.data();

	CSA_LOG("[eDVBCSAEngine] descramble: len=%d batch_size=%d", len, m_batch_size);

	while (i < len)
	{
		unsigned char *pkt = packets + i;

		const bool sync = isPacketValid(pkt);
		if (!sync || len - i < 188)
		{
			logBadPacket(sync ? "partial packet" : "sync loss", pkt, i, len);
			break;  // Still flush the batches collected so far
		}

		unsigned char scrambled = getScrambledBits(pkt);
		if (scrambled < 2) // clear or reserved
		{
			i += 188;
			continue;
		}

		const bool even = (scrambled == 2);

		/* HDSatelit 0.7.4: a parity change. The key of the new parity must be newer than at the end of its previous
		   period, or work on a PES start; otherwise the packets wait for the new key (see releaseHolds in csaengine.h).
		   The packets collected so far are descrambled first, with the keys they belong to. */
		const int parity = even ? 0 : 1;
		if (parity != m_parity)
		{
			if (m_parity >= 0)
			{
				if (even_cnt > 0)
				{
					pcks_even[even_cnt].data = NULL;
					g_csa_api.decrypt(key_even, pcks_even, 184);
					even_cnt = 0;
				}
				if (odd_cnt > 0)
				{
					pcks_odd[odd_cnt].data = NULL;
					g_csa_api.decrypt(key_odd, pcks_odd, 184);
					odd_cnt = 0;
				}
				m_gen_at_end[m_parity] = m_key_gen[m_parity].load(std::memory_order_acquire); // S8417: pairs with setKey
				g_csa_counters.flips.fetch_add(1, std::memory_order_relaxed);
				const unsigned gen = m_key_gen[parity].load(std::memory_order_acquire); // S8417: pairs with setKey
				/* the keys again, after the generation (setKey bumps it after the key slot swap, so the key read here is
				   at least that new): a control word come since the start of this buffer is used for the rest of it, not
				   the key of the previous period of this parity (the batches before the change are flushed above) */
				even_set = m_key_even_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
				odd_set = m_key_odd_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
				key_even = even_set ? m_key_even[m_key_even_idx.load(std::memory_order_acquire)] : nullptr; // S8417
				key_odd = odd_set ? m_key_odd[m_key_odd_idx.load(std::memory_order_acquire)] : nullptr; // S8417
				unsigned gen_key = gen;  // the generation of the key now in the snapshot
				const dvbcsa_bs_key_t* now_key = parity ? key_odd : key_even;
				/* at the boundary of two periods the PIDs change parity a little apart (audio before video), so the
				   stream goes back and forth: a return to a parity seen in this buffer or less than SAME_BOUNDARY_MS ago
				   is the same boundary, not a new period of it (11.11.2026: a wait of 2 s for a key that was not due) */
				const long long acum = nowMs();
				const bool recent = (parity ? seen_odd : seen_even) ||
					(m_seen_ms[parity] && acum - m_seen_ms[parity] < SAME_BOUNDARY_MS);
				if (now_key && !recent)
				{
					const long long lead = acum - m_key_changed_ms[parity].load(std::memory_order_relaxed);
					if (gen == m_gen_at_end[parity] && keyWorks(parity, now_key, packets, i, len) != 1)
					{
						g_csa_counters.late.fetch_add(1, std::memory_order_relaxed);
						if (m_holds_on.load(std::memory_order_acquire))
							waitForKey(parity, gen);
						gen_key = m_key_gen[parity].load(std::memory_order_acquire); // S8417: before the keys, as above
						even_set = m_key_even_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
						odd_set = m_key_odd_set.load(std::memory_order_acquire); // S8417: pairs with release in setKey()
						key_even = even_set ? m_key_even[m_key_even_idx.load(std::memory_order_acquire)] : nullptr; // S8417
						key_odd = odd_set ? m_key_odd[m_key_odd_idx.load(std::memory_order_acquire)] : nullptr; // S8417
						noteFlip(parity, gen, -(nowMs() - m_key_changed_ms[parity].load(std::memory_order_relaxed)), 0,
							nowMs() - acum);
					}
					else
						noteFlip(parity, gen, lead, gen == m_gen_at_end[parity] ? 1 : -1, 0);
					/* a key new for this period (merge=-1, or come during the wait) is checked below; the old key used after
					   a wait that ran out is counted already (asteptari_expirate), not as a wrong key of the line */
					m_check_pending[parity] = gen_key != m_gen_at_end[parity];
				}
			}
			m_parity = parity;
		}
		if (even)
			seen_even = true;
		else
			seen_odd = true;
		const dvbcsa_bs_key_t* key = even ? key_even : key_odd;
		if (m_check_pending[parity] && key && (pkt[1] & 0x40))
			checkKey(parity, key, packets, i);
		int offset = getPayloadOffset(pkt);

		if (!(pkt[3] & 0x10))
		{
			// Adaptation field only, nothing to descramble
			clearTSC(pkt);
		}
		else if (!key)
		{
			// No key: convert to null packet - no glitches
			setNullPacket(pkt);
			nulled++;
		}
		else if (offset >= 188)
		{
			// Never pass an invalid payload length to libdvbcsa, it aborts on it
			logBadPacket("adaptation field too long", pkt, i, len);
			setNullPacket(pkt);
			nulled++;
		}
		else
		{
			// Key available: descramble and clear TSC
			clearTSC(pkt);
			dvbcsa_bs_batch_s* batch = even ? pcks_even : pcks_odd;
			int& cnt = even ? even_cnt : odd_cnt;
			batch[cnt].data = pkt + offset;
			batch[cnt].len  = 188 - offset;
			cnt++;
			given++;
		}

		// flush even batch
		if (even_cnt == m_batch_size)
		{
			pcks_even[even_cnt].data = NULL;
			g_csa_api.decrypt(key_even, pcks_even, 184);
			CSA_LOG("[eDVBCSAEngine] decrypt even batch (%d)", m_batch_size);
			even_cnt = 0;
		}

		// flush odd batch
		if (odd_cnt == m_batch_size)
		{
			pcks_odd[odd_cnt].data = NULL;
			g_csa_api.decrypt(key_odd, pcks_odd, 184);
			CSA_LOG("[eDVBCSAEngine] decrypt odd batch (%d)", m_batch_size);
			odd_cnt = 0;
		}

		i += 188;
	}

	// flush remaining even
	if (even_cnt > 0)
	{
		pcks_even[even_cnt].data = NULL;
		g_csa_api.decrypt(key_even, pcks_even, 184);
		CSA_LOG("[eDVBCSAEngine] decrypt remaining even packets=%d", even_cnt);
	}

	// flush remaining odd
	if (odd_cnt > 0)
	{
		pcks_odd[odd_cnt].data = NULL;
		g_csa_api.decrypt(key_odd, pcks_odd, 184);
		CSA_LOG("[eDVBCSAEngine] decrypt remaining odd packets=%d", odd_cnt);
	}

	if (seen_even || seen_odd)
	{
		const long long acum = nowMs();
		if (seen_even)
			m_seen_ms[0] = acum;
		if (seen_odd)
			m_seen_ms[1] = acum;
	}
	if (given)
		g_csa_counters.descrambled.fetch_add(given, std::memory_order_relaxed);
	if (nulled)
		g_csa_counters.nulled.fetch_add(nulled, std::memory_order_relaxed);
	CSA_LOG("[eDVBCSAEngine] descramble done");
}
