/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-ocdm (libocdm.so): the OpenCDM interface (open_cdm.h) for WPE WebKit built with ENABLE_THUNDER, so that the
 * pages of the streaming services play their protected films in the navigator of the image (hds-navigator), with
 * the frames decoded by the board of the receiver (dvbvideosink / dvbaudiosink), as YouTube already does.
 *
 *  - "org.w3.clearkey": the keys come in the JSON answer of the page (W3C Clear Key), AES-128 with libgcrypt.
 *  - "com.widevine.alpha": the Widevine module (libwidevinecdm.so) that the receiver of the user downloads from
 *    Google after the user accepts the Google license (Components/HdsWidevineGoogle.py). It is used as any browser
 *    uses it, through the public CDM interface (content_decryption_module.h, CDM_MODULE_VERSION 4, interfaces 10 and
 *    11): this library is the host (memory, clock, timers, files) and passes the messages between the page and the
 *    module; the license requests go to the server of the service from the page itself (EME). Only Decrypt() is
 *    used: the module decrypts each sample on the processor and the sample stays compressed for the board decoder.
 *    Nothing in the module is changed and nothing of it is shipped by us.
 *
 * Threads: WebKit calls from its main thread and from the GStreamer streaming threads. Every call into the module
 * holds one lock (the module is not reentrant); the timers, the file answers and the other calls the module asks
 * for run on one worker thread of ours. The host functions that the module calls while it runs never take that
 * lock, and the callbacks towards WebKit are made from the worker thread, without any lock held.
 *
 * Environment: HDS_WIDEVINE_CDM (path of libwidevinecdm.so), HDS_OCDM_DATE (folder for the files of the module,
 * default $HOME/.local/share/hds-ocdm), HDS_OCDM_JURNAL=1 (more lines on stderr).
 */
#include "open_cdm.h"

#include <content_decryption_module.h>

#include <gcrypt.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <strings.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {

using Bytes = std::vector<uint8_t>;
using Clock = std::chrono::steady_clock;

const char* const kClearKey = "org.w3.clearkey";
const char* const kWidevine = "com.widevine.alpha";
const char* const kWidevineImplicit = "/home/root/.local/share/widevine/libwidevinecdm.so";

bool jurnalLung()
{
    static int v = -1;
    if (v < 0) {
        const char* e = getenv("HDS_OCDM_JURNAL");
        v = (e && *e == '1') ? 1 : 0;
    }
    return v == 1;
}

void jurnal(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void jurnal(const char* fmt, ...)
{
    char rand[600];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(rand, sizeof(rand), fmt, ap);
    va_end(ap);
    fprintf(stderr, "hds-ocdm: %s\n", rand);
}

std::string hex(const uint8_t* p, size_t n)
{
    static const char* d = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; i++) {
        s += d[p[i] >> 4];
        s += d[p[i] & 15];
    }
    return s;
}

std::string widevineCale()
{
    const char* e = getenv("HDS_WIDEVINE_CDM");
    return (e && *e) ? std::string(e) : std::string(kWidevineImplicit);
}

std::string dosarDate()
{
    const char* e = getenv("HDS_OCDM_DATE");
    if (e && *e)
        return e;
    const char* h = getenv("HOME");
    return std::string(h && *h ? h : "/tmp") + "/.local/share/hds-ocdm";
}

void facDosar(const std::string& cale)
{
    for (size_t i = 1; i <= cale.size(); i++) {
        if (i == cale.size() || cale[i] == '/')
            mkdir(cale.substr(0, i).c_str(), 0700);
    }
}

bool esteCheie(const char* a, const char* b) { return a && !strcmp(a, b); }

/* ------------------------------------------------------------------ base64url and the small JSON of Clear Key */

int b64val(char c)
{
    if (c >= 'A' && c <= 'Z')
        return c - 'A';
    if (c >= 'a' && c <= 'z')
        return c - 'a' + 26;
    if (c >= '0' && c <= '9')
        return c - '0' + 52;
    if (c == '-' || c == '+')
        return 62;
    if (c == '_' || c == '/')
        return 63;
    return -1;
}

bool b64dec(const std::string& s, Bytes& out)
{
    out.clear();
    unsigned acc = 0;
    int biti = 0;
    for (char c : s) {
        if (c == '=')
            break;
        int v = b64val(c);
        if (v < 0)
            return false;
        acc = (acc << 6) | (unsigned)v;
        biti += 6;
        if (biti >= 8) {
            biti -= 8;
            out.push_back((uint8_t)((acc >> biti) & 0xff));
        }
    }
    return true;
}

std::string b64urlenc(const uint8_t* p, size_t n)
{
    static const char* t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    std::string s;
    unsigned acc = 0;
    int biti = 0;
    for (size_t i = 0; i < n; i++) {
        acc = (acc << 8) | p[i];
        biti += 8;
        while (biti >= 6) {
            biti -= 6;
            s += t[(acc >> biti) & 63];
        }
    }
    if (biti)
        s += t[(acc << (6 - biti)) & 63];
    return s;
}

/* All the string values of the given name in a JSON text: "nume":"x" (lista false) or "nume":["x","y"] (lista true).
 * Enough for {"kids":[...]} and the JWK set {"keys":[{"kty":"oct","kid":"..","k":".."}]} (base64url, no escapes). */
std::vector<std::string> valoriJson(const std::string& j, const std::string& nume, bool lista)
{
    std::vector<std::string> r;
    std::string cheie = "\"" + nume + "\"";
    size_t poz = 0;
    while ((poz = j.find(cheie, poz)) != std::string::npos) {
        poz += cheie.size();
        size_t c = j.find_first_not_of(" \t\r\n", poz);
        if (c == std::string::npos || j[c] != ':')
            continue;
        c = j.find_first_not_of(" \t\r\n", c + 1);
        if (c == std::string::npos)
            break;
        if (lista) {
            if (j[c] != '[')
                continue;
            size_t sf = j.find(']', c);
            if (sf == std::string::npos)
                break;
            size_t q = j.find('"', c);
            while (q != std::string::npos && q < sf) {
                size_t q2 = j.find('"', q + 1);
                if (q2 == std::string::npos || q2 > sf)
                    break;
                r.push_back(j.substr(q + 1, q2 - q - 1));
                q = j.find('"', q2 + 1);
            }
        } else if (j[c] == '"') {
            size_t q2 = j.find('"', c + 1);
            if (q2 == std::string::npos)
                break;
            r.push_back(j.substr(c + 1, q2 - c - 1));
        }
    }
    return r;
}

uint32_t be32(const uint8_t* p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

/* The key IDs of the "pssh" boxes of version 1 (any system: the common one 1077efec... included) of a "cenc"
 * init data. */
std::vector<Bytes> kidsDinPssh(const uint8_t* d, size_t n)
{
    std::vector<Bytes> r;
    size_t i = 0;
    while (i + 32 <= n) {
        uint32_t marime = be32(d + i);
        if (marime < 32 || i + marime > n)
            break;
        if (!memcmp(d + i + 4, "pssh", 4) && d[i + 8] >= 1) {
            uint32_t k = be32(d + i + 28);
            size_t p = i + 32;
            for (uint32_t x = 0; x < k && p + 16 <= i + marime; x++, p += 16)
                r.emplace_back(d + p, d + p + 16);
        }
        i += marime;
    }
    return r;
}

/* ------------------------------------------------------------------ the objects behind the C handles */

class Modul;

struct Sesiune;

struct Sistem {
    std::string cheie;
    bool widevine = false;
    std::shared_ptr<Modul> modul;   // Widevine: one instance of the module per system (per MediaKeys)
};

struct Sesiune {
    std::atomic<int> ref { 1 };
    Sistem* sistem = nullptr;
    std::shared_ptr<Modul> modul;
    std::string id;
    LicenseType tip = Temporary;
    OpenCDMSessionCallbacks cb {};
    void* user = nullptr;
    std::map<Bytes, KeyStatus> stari;   // key ID -> state
    std::map<Bytes, Bytes> chei;        // Clear Key: key ID -> key
    std::atomic<bool> cheiAnuntate { false };   // Widevine: keys announced during the last UpdateSession
};

std::mutex g_lacat;                       // g_sesiuni and the key maps of every session
std::condition_variable g_cheiNoi;        // a key changed (opencdm_get_system_session waits for it)
std::vector<Sesiune*> g_sesiuni;          // every session alive (held by WebKit or by a pending callback)
std::atomic<unsigned> g_numar { 0 };

OpenCDMSession* manier(Sesiune* s) { return reinterpret_cast<OpenCDMSession*>(s); }   // the C handle of a session
void tine(Sesiune* s) { s->ref++; }
void lasa(Sesiune* s);

/* "N:Type:<payload>" towards WebKit (CDMThunder.cpp, ParsedResponseMessage) */
void anuntaProvocare(Sesiune* s, unsigned tip, const uint8_t* p, size_t n)
{
    if (!s->cb.process_challenge_callback)
        return;
    Bytes m;
    char cap[16];
    snprintf(cap, sizeof(cap), "%u:Type:", tip > 9 ? 0u : tip);
    m.insert(m.end(), cap, cap + 7);
    m.insert(m.end(), p, p + n);
    if (m.size() > 0xffff) {
        jurnal("mesaj de %zu octeti, prea lung pentru OpenCDM", m.size());
        if (s->cb.error_message_callback)
            s->cb.error_message_callback(manier(s), s->user, "message too long");
        return;
    }
    s->cb.process_challenge_callback(manier(s), s->user, "", m.data(), (uint16_t)m.size());
}

void anuntaChei(Sesiune* s, const std::vector<Bytes>& kids)
{
    for (const Bytes& k : kids) {
        if (s->cb.key_update_callback)
            s->cb.key_update_callback(manier(s), s->user, k.data(), (uint8_t)std::min<size_t>(k.size(), 255));
    }
    if (s->cb.keys_updated_callback)
        s->cb.keys_updated_callback(manier(s), s->user);
    g_cheiNoi.notify_all();
}

KeyStatus dinCdm(cdm::KeyStatus k)
{
    switch (k) {
    case cdm::kUsable: return Usable;
    case cdm::kInternalError: return InternalError;
    case cdm::kExpired: return Expired;
    case cdm::kOutputRestricted: return OutputRestricted;
    case cdm::kOutputDownscaled: return OutputDownscaled;
    case cdm::kStatusPending: return StatusPending;
    case cdm::kReleased: return Released;
    }
    return InternalError;
}

/* ------------------------------------------------------------------ Clear Key: AES-128 on the processor */

bool aesInit()
{
    static std::once_flag o;
    static bool bun = false;
    std::call_once(o, [] {
        bun = gcry_check_version(nullptr) != nullptr;
        if (bun) {
            gcry_control(GCRYCTL_DISABLE_SECMEM, 0);
            gcry_control(GCRYCTL_INITIALIZATION_FINISHED, 0);
        }
    });
    return bun;
}

/* cenc: the encrypted parts of all subsamples form one AES-CTR stream (IV of 8 bytes padded with zeros).
 * cbcs: AES-CBC on each subsample from the same IV, crypt_byte_block blocks encrypted then skip_byte_block clear
 * (0 and 0: every block), a last partial block stays clear. */
OpenCDMError decripteazaAes(const Bytes& cheie, uint32_t schema, uint8_t* d, uint32_t n, const uint8_t* iv, uint32_t ivn,
    const HdsOcdmSubsample* sub, uint32_t nsub, uint32_t crypt, uint32_t skip)
{
    if (schema == 0)
        return ERROR_NONE;
    if (!aesInit() || cheie.size() != 16)
        return ERROR_UNKNOWN;
    uint8_t iv16[16] = {};
    memcpy(iv16, iv, std::min<uint32_t>(ivn, 16));
    HdsOcdmSubsample tot = { 0, n };
    if (!nsub) {
        sub = &tot;
        nsub = 1;
    }
    uint64_t suma = 0;
    for (uint32_t i = 0; i < nsub; i++)
        suma += (uint64_t)sub[i].clear_bytes + sub[i].cipher_bytes;
    if (suma > n)
        return ERROR_INVALID_DECRYPT_BUFFER;
    gcry_cipher_hd_t h;
    int mod = schema == 2 ? GCRY_CIPHER_MODE_CBC : GCRY_CIPHER_MODE_CTR;
    if (gcry_cipher_open(&h, GCRY_CIPHER_AES128, mod, 0))
        return ERROR_UNKNOWN;
    OpenCDMError r = ERROR_NONE;
    if (gcry_cipher_setkey(h, cheie.data(), 16))
        r = ERROR_UNKNOWN;
    if (r == ERROR_NONE && schema != 2 && gcry_cipher_setctr(h, iv16, 16))
        r = ERROR_UNKNOWN;
    uint8_t* p = d;
    for (uint32_t i = 0; r == ERROR_NONE && i < nsub; i++) {
        p += sub[i].clear_bytes;
        uint32_t c = sub[i].cipher_bytes;
        if (schema != 2) {
            if (c && gcry_cipher_decrypt(h, p, c, nullptr, 0))
                r = ERROR_UNKNOWN;
        } else if (c >= 16) {
            if (gcry_cipher_setiv(h, iv16, 16)) {
                r = ERROR_UNKNOWN;
                break;
            }
            uint32_t cr = crypt, sk = skip;
            if (!cr && !sk)
                cr = 1;
            uint8_t* q = p;
            uint32_t rest = c - c % 16;
            while (rest && r == ERROR_NONE) {
                uint32_t blocuri = std::min<uint32_t>(cr, rest / 16);
                if (blocuri && gcry_cipher_decrypt(h, q, blocuri * 16, nullptr, 0))
                    r = ERROR_UNKNOWN;
                q += blocuri * 16;
                rest -= blocuri * 16;
                uint32_t sar = std::min<uint32_t>(sk * 16, rest);
                q += sar;
                rest -= sar;
            }
        }
        p += c;
    }
    gcry_cipher_close(h);
    return r;
}

/* ------------------------------------------------------------------ Widevine: the module and its host */

/* The calls we make, the same for interfaces 11 and 10 (same names, same arguments). */
class ApelCdm {
public:
    virtual ~ApelCdm() { }
    virtual void Initialize(bool a, bool b, bool c) = 0;
    virtual void SetServerCertificate(uint32_t p, const uint8_t* d, uint32_t n) = 0;
    virtual void CreateSessionAndGenerateRequest(uint32_t p, cdm::SessionType t, cdm::InitDataType i, const uint8_t* d, uint32_t n) = 0;
    virtual void LoadSession(uint32_t p, cdm::SessionType t, const char* id, uint32_t n) = 0;
    virtual void UpdateSession(uint32_t p, const char* id, uint32_t idn, const uint8_t* d, uint32_t n) = 0;
    virtual void CloseSession(uint32_t p, const char* id, uint32_t n) = 0;
    virtual void RemoveSession(uint32_t p, const char* id, uint32_t n) = 0;
    virtual void TimerExpired(void* c) = 0;
    virtual cdm::Status Decrypt(const cdm::InputBuffer_2& in, cdm::DecryptedBlock* out) = 0;
    virtual void OnPlatformChallengeResponse(const cdm::PlatformChallengeResponse& r) = 0;
    virtual void OnQueryOutputProtectionStatus(cdm::QueryResult r, uint32_t l, uint32_t m) = 0;
    virtual void OnStorageId(uint32_t v, const uint8_t* d, uint32_t n) = 0;
    virtual void Destroy() = 0;
    virtual int versiune() const = 0;
};

template<typename T> class ApelCdmT final : public ApelCdm {
public:
    explicit ApelCdmT(T* m) : c(m) { }
    void Initialize(bool a, bool b, bool d) override { c->Initialize(a, b, d); }
    void SetServerCertificate(uint32_t p, const uint8_t* d, uint32_t n) override { c->SetServerCertificate(p, d, n); }
    void CreateSessionAndGenerateRequest(uint32_t p, cdm::SessionType t, cdm::InitDataType i, const uint8_t* d, uint32_t n) override
    {
        c->CreateSessionAndGenerateRequest(p, t, i, d, n);
    }
    void LoadSession(uint32_t p, cdm::SessionType t, const char* id, uint32_t n) override { c->LoadSession(p, t, id, n); }
    void UpdateSession(uint32_t p, const char* id, uint32_t idn, const uint8_t* d, uint32_t n) override { c->UpdateSession(p, id, idn, d, n); }
    void CloseSession(uint32_t p, const char* id, uint32_t n) override { c->CloseSession(p, id, n); }
    void RemoveSession(uint32_t p, const char* id, uint32_t n) override { c->RemoveSession(p, id, n); }
    void TimerExpired(void* x) override { c->TimerExpired(x); }
    cdm::Status Decrypt(const cdm::InputBuffer_2& in, cdm::DecryptedBlock* out) override { return c->Decrypt(in, out); }
    void OnPlatformChallengeResponse(const cdm::PlatformChallengeResponse& r) override { c->OnPlatformChallengeResponse(r); }
    void OnQueryOutputProtectionStatus(cdm::QueryResult r, uint32_t l, uint32_t m) override { c->OnQueryOutputProtectionStatus(r, l, m); }
    void OnStorageId(uint32_t v, const uint8_t* d, uint32_t n) override { c->OnStorageId(v, d, n); }
    void Destroy() override { c->Destroy(); c = nullptr; }
    int versiune() const override { return T::kVersion; }
private:
    T* c;
};

struct Bufer final : public cdm::Buffer {
    explicit Bufer(uint32_t c) : mem(c ? c : 1) { }
    void Destroy() override { delete this; }
    uint32_t Capacity() const override { return (uint32_t)mem.size(); }
    uint8_t* Data() override { return mem.data(); }
    void SetSize(uint32_t s) override { marime = std::min<uint32_t>(s, (uint32_t)mem.size()); }
    uint32_t Size() const override { return marime; }
    Bytes mem;
    uint32_t marime = 0;
};

struct BlocDecriptat final : public cdm::DecryptedBlock {
    ~BlocDecriptat() override
    {
        if (b)
            b->Destroy();
    }
    void SetDecryptedBuffer(cdm::Buffer* x) override
    {
        if (b && b != x)
            b->Destroy();
        b = x;
    }
    cdm::Buffer* DecryptedBuffer() override { return b; }
    void SetTimestamp(int64_t t) override { ts = t; }
    int64_t Timestamp() const override { return ts; }
    cdm::Buffer* b = nullptr;
    int64_t ts = 0;
};

struct Promisiune {
    bool gata = false;
    bool bun = false;
    std::string sesiune;
    std::string eroare;
};

class Modul final : public cdm::Host_11, public cdm::Host_10 {
public:
    static std::shared_ptr<Modul> creeaza(std::string& eroare);
    ~Modul() override;

    /* one call into the module, now, on the calling thread */
    template<typename F> void acum(F f)
    {
        std::lock_guard<std::mutex> l(m_cdm);
        if (m_apel)
            f(*m_apel);
    }
    /* one call into the module, later, on the worker thread */
    void maiTarziu(int64_t dupaMs, std::function<void(ApelCdm&)> f)
    {
        lucru(dupaMs, [this, f] {
            std::lock_guard<std::mutex> l(m_cdm);
            if (m_apel)
                f(*m_apel);
        });
    }
    /* anything on the worker thread, without the lock of the module (the callbacks towards WebKit) */
    void lucru(int64_t dupaMs, std::function<void()> f);

    uint32_t promisiuneNoua();
    uint32_t promisiuneFaraAsteptare()   // a promise nobody waits for (UpdateSession): no entry in m_promisiuni
    {
        std::lock_guard<std::mutex> l(m_p);
        return ++m_urm;
    }
    Promisiune asteapta(uint32_t id, int ms);
    void inregistreaza(Sesiune* s);
    void scoate(Sesiune* s);
    void legaActualizare(uint32_t promisiune, Sesiune* s);

    // cdm::Host_11 and cdm::Host_10, called by the module while it runs (no lock of the module taken here)
    cdm::Buffer* Allocate(uint32_t capacity) override { return new Bufer(capacity); }
    void SetTimer(int64_t delay_ms, void* context) override
    {
        maiTarziu(delay_ms, [context](ApelCdm& c) { c.TimerExpired(context); });
    }
    cdm::Time GetCurrentWallTime() override
    {
        struct timeval tv;
        gettimeofday(&tv, nullptr);
        return tv.tv_sec + tv.tv_usec / 1e6;
    }
    void OnInitialized(bool success) override;
    void OnResolveKeyStatusPromise(uint32_t promise_id, cdm::KeyStatus) override { rezolva(promise_id, true, "", ""); }
    void OnResolveNewSessionPromise(uint32_t promise_id, const char* session_id, uint32_t n) override
    {
        rezolva(promise_id, true, std::string(session_id, n), "");
    }
    void OnResolvePromise(uint32_t promise_id) override;
    void OnRejectPromise(uint32_t promise_id, cdm::Exception, uint32_t system_code, const char* msg, uint32_t n) override;
    void OnSessionMessage(const char* session_id, uint32_t sn, cdm::MessageType tip, const char* msg, uint32_t n) override;
    void OnSessionKeysChange(const char* session_id, uint32_t sn, bool, const cdm::KeyInformation* keys, uint32_t nk) override;
    void OnExpirationChange(const char*, uint32_t, cdm::Time) override { }
    void OnSessionClosed(const char*, uint32_t) override { }
    void SendPlatformChallenge(const char*, uint32_t, const char*, uint32_t) override
    {
        // the attestation of the platform exists only on ChromeOS; as on a Linux PC, the answer is empty
        maiTarziu(0, [](ApelCdm& c) {
            cdm::PlatformChallengeResponse r = {};
            c.OnPlatformChallengeResponse(r);
        });
    }
    void EnableOutputProtection(uint32_t) override { }
    void QueryOutputProtectionStatus() override
    {
        // What a Linux PC without information about its outputs answers: the query worked, no link known, no
        // protection. HDCP is not claimed: the keys that need it stay refused by the module.
        maiTarziu(0, [](ApelCdm& c) { c.OnQueryOutputProtectionStatus(cdm::kQuerySucceeded, 0, 0); });
    }
    void OnDeferredInitializationDone(cdm::StreamType, cdm::Status) override { }
    cdm::FileIO* CreateFileIO(cdm::FileIOClient* client) override;
    void RequestStorageId(uint32_t version) override
    {
        maiTarziu(0, [version](ApelCdm& c) { c.OnStorageId(version, nullptr, 0); });
    }

    std::string dosar;
    int versiune() const { return m_apel ? m_apel->versiune() : 0; }

private:
    Modul() = default;
    void rezolva(uint32_t id, bool bun, const std::string& sesiune, const std::string& eroare);
    void bucla();
    Sesiune* gaseste(const std::string& id);   // with one more reference, under m_s
    Sesiune* luaActualizare(uint32_t promisiune);

    std::unique_ptr<ApelCdm> m_apel;
    std::mutex m_cdm;

    std::mutex m_p;
    std::condition_variable m_pc;
    std::map<uint32_t, Promisiune> m_promisiuni;
    uint32_t m_urm = 0;
    int m_init = -1;

    std::mutex m_s;
    std::map<std::string, Sesiune*> m_sesiuni;
    std::map<std::string, std::vector<std::pair<unsigned, Bytes>>> m_asteptate;   // messages before the session id
    std::map<uint32_t, Sesiune*> m_actualizari;   // promise of an UpdateSession -> session (held)

    std::mutex m_q;
    std::condition_variable m_qc;
    std::multimap<Clock::time_point, std::function<void()>> m_coada;
    bool m_opreste = false;
    std::thread m_fir;
};

/* One file of the module in its folder; the answers go through the worker thread, under the lock of the module. */
class FisierCdm final : public cdm::FileIO {
public:
    FisierCdm(Modul* m, cdm::FileIOClient* c) : modul(m), client(c) { }
    void Open(const char* nume, uint32_t n) override
    {
        std::string f(nume, n);
        bool bun = !f.empty() && f.size() < 200 && f[0] != '.';
        for (char ch : f)
            bun = bun && (isalnum((unsigned char)ch) || ch == '.' || ch == '_' || ch == '-');
        cale = bun ? modul->dosar + "/" + f : std::string();
        cdm::FileIOClient* cl = client;
        modul->maiTarziu(0, [cl, bun](ApelCdm&) {
            cl->OnOpenComplete(bun ? cdm::FileIOClient::Status::kSuccess : cdm::FileIOClient::Status::kError);
        });
    }
    void Read() override
    {
        auto date = std::make_shared<Bytes>();
        bool bun = !cale.empty();
        if (bun) {
            std::ifstream in(cale, std::ios::binary);
            if (in)
                date->assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
        }
        cdm::FileIOClient* cl = client;
        modul->maiTarziu(0, [cl, bun, date](ApelCdm&) {
            cl->OnReadComplete(bun ? cdm::FileIOClient::Status::kSuccess : cdm::FileIOClient::Status::kError,
                date->empty() ? nullptr : date->data(), (uint32_t)date->size());
        });
    }
    void Write(const uint8_t* d, uint32_t n) override
    {
        bool bun = !cale.empty();
        if (bun) {
            if (!n)
                unlink(cale.c_str());
            else {
                std::string tmp = cale + ".nou";
                std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
                out.write(reinterpret_cast<const char*>(d), n);
                out.close();
                bun = out.good() && !rename(tmp.c_str(), cale.c_str());
            }
        }
        cdm::FileIOClient* cl = client;
        modul->maiTarziu(0, [cl, bun](ApelCdm&) {
            cl->OnWriteComplete(bun ? cdm::FileIOClient::Status::kSuccess : cdm::FileIOClient::Status::kError);
        });
    }
    void Close() override
    {
        // the answers already queued may still use the client, not this object
        FisierCdm* x = this;
        modul->lucru(0, [x] { delete x; });
    }
private:
    Modul* modul;
    cdm::FileIOClient* client;
    std::string cale;
};

cdm::FileIO* Modul::CreateFileIO(cdm::FileIOClient* client) { return new FisierCdm(this, client); }

void* gazdaPentru(int versiune, void* user)
{
    Modul* m = static_cast<Modul*>(user);
    if (versiune == cdm::Host_11::kVersion)
        return static_cast<cdm::Host_11*>(m);
    if (versiune == cdm::Host_10::kVersion)
        return static_cast<cdm::Host_10*>(m);
    return nullptr;
}

std::shared_ptr<Modul> Modul::creeaza(std::string& eroare)
{
    static std::mutex incarcare;
    static void* lib = nullptr;
    std::lock_guard<std::mutex> lk(incarcare);
    std::string cale = widevineCale();
    if (!lib) {
        if (access(cale.c_str(), R_OK)) {
            eroare = "modulul Widevine lipseste sau nu se poate citi: " + cale;
            return nullptr;
        }
        // libwidevinecdm.so (ChromeOS, ARM pe 32 de biti) cere functiile ARM ale lui libgcc (__aeabi_uidiv), globale
        dlopen("libgcc_s.so.1", RTLD_NOW | RTLD_GLOBAL);
        lib = dlopen(cale.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!lib) {
            const char* e = dlerror();
            eroare = std::string("dlopen: ") + (e ? e : "?");
            return nullptr;
        }
        typedef void (*InitFn)();
        auto init = reinterpret_cast<InitFn>(dlsym(lib, "InitializeCdmModule_4"));
        if (init)
            init();
    }
    typedef void* (*CreateFn)(int, const char*, uint32_t, GetCdmHostFunc, void*);
    typedef const char* (*VersionFn)();
    auto create = reinterpret_cast<CreateFn>(dlsym(lib, "CreateCdmInstance"));
    auto version = reinterpret_cast<VersionFn>(dlsym(lib, "GetCdmVersion"));
    if (!create) {
        eroare = "modulul nu are CreateCdmInstance";
        return nullptr;
    }
    std::shared_ptr<Modul> m(new Modul());
    m->dosar = dosarDate();
    facDosar(m->dosar);
    Modul* mp = m.get();
    m->m_fir = std::thread([mp] { mp->bucla(); });
    const uint32_t ksn = (uint32_t)strlen(kWidevine);
    {
        std::lock_guard<std::mutex> l(m->m_cdm);
        // 10 intai: interfata stabila din 2018, cu care e facut modulul din 2023; 11 era atunci experimentala (antetul de la
        // SRCREV-ul retetei, din 2022, e cel de atunci; 11 de acum, stabila din 12.2024, are alta forma)
        if (void* c = create(cdm::ContentDecryptionModule_10::kVersion, kWidevine, ksn, gazdaPentru, mp))
            m->m_apel.reset(new ApelCdmT<cdm::ContentDecryptionModule_10>(static_cast<cdm::ContentDecryptionModule_10*>(c)));
        else if (void* c11 = create(cdm::ContentDecryptionModule_11::kVersion, kWidevine, ksn, gazdaPentru, mp))
            m->m_apel.reset(new ApelCdmT<cdm::ContentDecryptionModule_11>(static_cast<cdm::ContentDecryptionModule_11*>(c11)));
    }
    if (!m->m_apel) {
        eroare = "CreateCdmInstance a refuzat interfetele 10 si 11";
        return nullptr;
    }
    jurnal("modulul Widevine %s, interfata CDM %d", version ? version() : "?", m->versiune());
    // fara identificator distinctiv, cu fisierele modulului permise (dosarul lui), fara decodoare sigure in hardware
    m->acum([](ApelCdm& c) { c.Initialize(false, true, false); });
    std::unique_lock<std::mutex> l(m->m_p);
    m->m_pc.wait_for(l, std::chrono::seconds(10), [mp] { return mp->m_init >= 0; });
    if (m->m_init != 1) {
        eroare = m->m_init < 0 ? "modulul nu a raspuns la Initialize" : "modulul a refuzat Initialize";
        return nullptr;
    }
    return m;
}

Modul::~Modul()
{
    {
        std::lock_guard<std::mutex> l(m_q);
        m_opreste = true;
    }
    m_qc.notify_all();
    if (m_fir.joinable()) {
        if (m_fir.get_id() == std::this_thread::get_id())
            m_fir.detach();
        else
            m_fir.join();
    }
    std::lock_guard<std::mutex> l(m_cdm);
    if (m_apel)
        m_apel->Destroy();
    m_apel.reset();
    // the library stays loaded (other systems, and the threads of the module itself)
}

void Modul::bucla()
{
    std::unique_lock<std::mutex> l(m_q);
    while (!m_opreste) {
        if (m_coada.empty()) {
            m_qc.wait(l);
            continue;
        }
        auto prima = m_coada.begin();
        if (prima->first > Clock::now()) {
            m_qc.wait_until(l, prima->first);
            continue;
        }
        auto f = std::move(prima->second);
        m_coada.erase(prima);
        l.unlock();
        f();
        l.lock();
    }
}

void Modul::lucru(int64_t dupaMs, std::function<void()> f)
{
    {
        std::lock_guard<std::mutex> l(m_q);
        m_coada.emplace(Clock::now() + std::chrono::milliseconds(std::max<int64_t>(dupaMs, 0)), std::move(f));
    }
    m_qc.notify_all();
}

uint32_t Modul::promisiuneNoua()
{
    std::lock_guard<std::mutex> l(m_p);
    uint32_t id = ++m_urm;
    m_promisiuni[id] = Promisiune();
    return id;
}

void Modul::OnInitialized(bool success)
{
    {
        std::lock_guard<std::mutex> l(m_p);
        m_init = success ? 1 : 0;
    }
    m_pc.notify_all();
}

void Modul::rezolva(uint32_t id, bool bun, const std::string& sesiune, const std::string& eroare)
{
    {
        std::lock_guard<std::mutex> l(m_p);
        auto it = m_promisiuni.find(id);
        if (it == m_promisiuni.end())
            return;
        it->second.gata = true;
        it->second.bun = bun;
        it->second.sesiune = sesiune;
        it->second.eroare = eroare;
    }
    m_pc.notify_all();
}

Promisiune Modul::asteapta(uint32_t id, int ms)
{
    std::unique_lock<std::mutex> l(m_p);
    m_pc.wait_for(l, std::chrono::milliseconds(ms), [this, id] { return m_promisiuni[id].gata; });
    Promisiune p = m_promisiuni[id];
    m_promisiuni.erase(id);
    if (!p.gata)
        p.eroare = "fara raspuns de la modul";
    return p;
}

Sesiune* Modul::gaseste(const std::string& id)
{
    auto it = m_sesiuni.find(id);
    if (it == m_sesiuni.end())
        return nullptr;
    // never bring back a session whose last reference is gone (lasa is removing it)
    int r = it->second->ref.load();
    while (r > 0 && !it->second->ref.compare_exchange_weak(r, r + 1)) { }
    return r > 0 ? it->second : nullptr;
}

void Modul::legaActualizare(uint32_t promisiune, Sesiune* s)
{
    tine(s);
    std::lock_guard<std::mutex> l(m_s);
    m_actualizari[promisiune] = s;
}

Sesiune* Modul::luaActualizare(uint32_t promisiune)
{
    std::lock_guard<std::mutex> l(m_s);
    auto it = m_actualizari.find(promisiune);
    if (it == m_actualizari.end())
        return nullptr;
    Sesiune* s = it->second;
    m_actualizari.erase(it);
    return s;
}

void Modul::OnResolvePromise(uint32_t promise_id)
{
    rezolva(promise_id, true, "", "");
    if (Sesiune* s = luaActualizare(promise_id)) {
        if (s->cheiAnuntate) {
            lasa(s);   // keys_updated already goes with the keys (OnSessionKeysChange)
            return;
        }
        // the answer of the server was taken but no key changed (a renewal): WebKit still waits for keys_updated
        lucru(0, [s] {
            if (s->cb.keys_updated_callback)
                s->cb.keys_updated_callback(manier(s), s->user);
            lasa(s);
        });
    }
}

void Modul::OnRejectPromise(uint32_t promise_id, cdm::Exception, uint32_t system_code, const char* msg, uint32_t n)
{
    std::string e(msg && n ? std::string(msg, n) : std::string());
    jurnal("modulul a refuzat cererea %u: %s (cod %u)", promise_id, e.c_str(), system_code);
    rezolva(promise_id, false, "", e);
    if (Sesiune* s = luaActualizare(promise_id)) {
        std::string text = e.empty() ? std::string("license update rejected") : e;
        lucru(0, [s, text] {
            if (s->cb.error_message_callback)
                s->cb.error_message_callback(manier(s), s->user, text.c_str());
            lasa(s);
        });
    }
}

void Modul::OnSessionMessage(const char* session_id, uint32_t sn, cdm::MessageType tip, const char* msg, uint32_t n)
{
    std::string id(session_id, sn);
    Bytes m(reinterpret_cast<const uint8_t*>(msg), reinterpret_cast<const uint8_t*>(msg) + n);
    if (jurnalLung())
        jurnal("mesajul %u (%u octeti) pentru sesiunea %s", (unsigned)tip, n, id.c_str());
    Sesiune* s;
    {
        std::lock_guard<std::mutex> l(m_s);
        s = gaseste(id);
        if (!s) {
            m_asteptate[id].emplace_back((unsigned)tip, std::move(m));
            return;
        }
    }
    unsigned t = (unsigned)tip;
    lucru(0, [s, t, m] {
        anuntaProvocare(s, t, m.data(), m.size());
        lasa(s);
    });
}

void Modul::OnSessionKeysChange(const char* session_id, uint32_t sn, bool, const cdm::KeyInformation* keys, uint32_t nk)
{
    Sesiune* s;
    {
        std::lock_guard<std::mutex> l(m_s);
        s = gaseste(std::string(session_id, sn));
    }
    if (!s)
        return;
    std::vector<Bytes> kids;
    {
        std::lock_guard<std::mutex> l(g_lacat);
        for (uint32_t i = 0; i < nk; i++) {
            Bytes k(keys[i].key_id, keys[i].key_id + keys[i].key_id_size);
            s->stari[k] = dinCdm(keys[i].status);
            s->cheiAnuntate = true;
            kids.push_back(k);
            if (jurnalLung() || keys[i].status != cdm::kUsable)
                jurnal("cheia %s: starea %u", hex(k.data(), k.size()).c_str(), (unsigned)keys[i].status);
        }
    }
    lucru(0, [s, kids] {
        anuntaChei(s, kids);
        lasa(s);
    });
}

void Modul::inregistreaza(Sesiune* s)
{
    std::vector<std::pair<unsigned, Bytes>> asteptate;
    {
        std::lock_guard<std::mutex> l(m_s);
        m_sesiuni[s->id] = s;
        auto it = m_asteptate.find(s->id);
        if (it != m_asteptate.end()) {
            asteptate = std::move(it->second);
            m_asteptate.erase(it);
        }
    }
    for (auto& m : asteptate) {
        tine(s);
        unsigned t = m.first;
        auto b = std::make_shared<Bytes>(std::move(m.second));
        lucru(0, [s, t, b] {
            anuntaProvocare(s, t, b->data(), b->size());
            lasa(s);
        });
    }
}

void Modul::scoate(Sesiune* s)
{
    std::lock_guard<std::mutex> l(m_s);
    auto it = m_sesiuni.find(s->id);
    if (it != m_sesiuni.end() && it->second == s)
        m_sesiuni.erase(it);
}

/* ------------------------------------------------------------------ the sessions */

void lasa(Sesiune* s)
{
    {
        // under the same lock as opencdm_get_system_session, which may take a new reference meanwhile
        std::lock_guard<std::mutex> l(g_lacat);
        if (--s->ref > 0)
            return;
        g_sesiuni.erase(std::remove(g_sesiuni.begin(), g_sesiuni.end(), s), g_sesiuni.end());
    }
    if (s->modul)
        s->modul->scoate(s);
    std::shared_ptr<Modul> m = std::move(s->modul);
    delete s;
    // the reference to the module is always dropped on a thread of its own: the last one must never go on the worker
    // thread of the module or while the module runs (with the lock of the module held)
    if (m) {
        auto ultim = std::make_shared<std::shared_ptr<Modul>>(std::move(m));
        std::thread([ultim] { ultim->reset(); }).detach();
    }
}

cdm::InitDataType tipInit(const char* t)
{
    if (t && !strcasecmp(t, "keyids"))
        return cdm::kKeyIds;
    if (t && !strcasecmp(t, "webm"))
        return cdm::kWebM;
    return cdm::kCenc;   // "cenc" and "cbcs"
}

/* Clear Key: the license request is {"kids":[...],"type":"temporary"} (W3C Clear Key). */
OpenCDMError clearKeyConstruieste(Sesiune* s, const char* tip, const uint8_t* d, uint32_t n)
{
    std::vector<Bytes> kids;
    if (tip && !strcasecmp(tip, "keyids")) {
        std::string j(reinterpret_cast<const char*>(d), n);
        for (const std::string& k : valoriJson(j, "kids", true)) {
            Bytes b;
            if (b64dec(k, b) && !b.empty())
                kids.push_back(b);
        }
    } else if (tip && (!strcasecmp(tip, "cenc") || !strcasecmp(tip, "cbcs")))
        kids = kidsDinPssh(d, n);
    else if (tip && !strcasecmp(tip, "webm") && n)
        kids.emplace_back(d, d + n);
    if (kids.empty())
        return ERROR_INVALID_SESSION;
    std::string j = "{\"kids\":[";
    for (size_t i = 0; i < kids.size(); i++)
        j += (i ? ",\"" : "\"") + b64urlenc(kids[i].data(), kids[i].size()) + "\"";
    j += std::string("],\"type\":\"") + (s->tip == Temporary ? "temporary" : "persistent-license") + "\"}";
    {
        std::lock_guard<std::mutex> l(g_lacat);
        for (const Bytes& k : kids)
            s->stari[k] = StatusPending;
    }
    s->id = "ck" + std::to_string(++g_numar);
    anuntaProvocare(s, 0, reinterpret_cast<const uint8_t*>(j.data()), j.size());
    return ERROR_NONE;
}

OpenCDMError clearKeyActualizeaza(Sesiune* s, const uint8_t* d, uint32_t n)
{
    std::string j(reinterpret_cast<const char*>(d), n);
    std::vector<std::string> kid = valoriJson(j, "kid", false), k = valoriJson(j, "k", false);
    if (kid.empty() || kid.size() != k.size())
        return ERROR_INVALID_SESSION;
    std::vector<Bytes> kids;
    {
        std::lock_guard<std::mutex> l(g_lacat);
        for (size_t i = 0; i < kid.size(); i++) {
            Bytes a, b;
            if (!b64dec(kid[i], a) || !b64dec(k[i], b) || b.size() != 16)
                continue;
            s->chei[a] = b;
            s->stari[a] = Usable;
            kids.push_back(a);
        }
    }
    if (kids.empty())
        return ERROR_INVALID_SESSION;
    anuntaChei(s, kids);
    return ERROR_NONE;
}

std::shared_ptr<Modul> modulPentru(Sistem* s, std::string& eroare)
{
    static std::mutex m;
    std::lock_guard<std::mutex> l(m);
    if (!s->modul) {
        s->modul = Modul::creeaza(eroare);
    }
    return s->modul;
}

} // namespace

/* ================================================================== the C interface */

extern "C" {

OpenCDMError opencdm_is_type_supported(const char keySystem[], const char mimeType[])
{
    bool cheie = esteCheie(keySystem, kClearKey) || (esteCheie(keySystem, kWidevine) && !access(widevineCale().c_str(), R_OK));
    if (!cheie)
        return ERROR_KEYSYSTEM_NOT_SUPPORTED;
    if (!mimeType || !*mimeType)
        return ERROR_NONE;
    // what the board decodes (the quirk hdsdvb keeps VP8/VP9/AV1/HEVC/Opus out of the navigator)
    std::string m(mimeType);
    std::transform(m.begin(), m.end(), m.begin(), [](unsigned char c) { return (char)tolower(c); });
    if (m.find("video/mp4") != 0 && m.find("audio/mp4") != 0 && m.find("video/webm") != 0 && m.find("audio/webm") != 0)
        return ERROR_KEYSYSTEM_NOT_SUPPORTED;
    size_t c = m.find("codecs");
    if (c == std::string::npos)
        return ERROR_NONE;
    std::string lista = m.substr(c + 6);
    const char* bune[] = { "avc1", "avc3", "mp4a", "ac-3", "ec-3" };
    size_t i = 0;
    while (i < lista.size()) {
        while (i < lista.size() && (lista[i] == '=' || lista[i] == '"' || lista[i] == '\'' || lista[i] == ',' || lista[i] == ' '))
            i++;
        size_t j = i;
        while (j < lista.size() && lista[j] != ',' && lista[j] != '"' && lista[j] != '\'' && lista[j] != ' ')
            j++;
        if (j > i) {
            std::string codec = lista.substr(i, j - i);
            bool bun = false;
            for (const char* b : bune)
                bun = bun || codec.compare(0, strlen(b), b) == 0;
            if (!bun)
                return ERROR_KEYSYSTEM_NOT_SUPPORTED;
        }
        i = j + 1;
    }
    return ERROR_NONE;
}

OpenCDMSystem* opencdm_create_system(const char keySystem[])
{
    if (!esteCheie(keySystem, kClearKey) && !esteCheie(keySystem, kWidevine))
        return nullptr;
    Sistem* s = new Sistem();
    s->cheie = keySystem;
    s->widevine = esteCheie(keySystem, kWidevine);
    return reinterpret_cast<OpenCDMSystem*>(s);
}

OpenCDMError opencdm_destruct_system(OpenCDMSystem* system)
{
    Sistem* s = reinterpret_cast<Sistem*>(system);
    if (!s)
        return ERROR_INVALID_ACCESSOR;
    {
        std::lock_guard<std::mutex> l(g_lacat);
        for (Sesiune* x : g_sesiuni) {
            if (x->sistem == s)
                x->sistem = nullptr;
        }
    }
    std::shared_ptr<Modul> m = std::move(s->modul);
    delete s;
    m.reset();
    return ERROR_NONE;
}

bool opencdm_system_supports_server_certificate(OpenCDMSystem* system)
{
    Sistem* s = reinterpret_cast<Sistem*>(system);
    return s && s->widevine;
}

OpenCDMError opencdm_system_set_server_certificate(OpenCDMSystem* system, const uint8_t serverCertificate[],
    const uint32_t serverCertificateLength)
{
    Sistem* s = reinterpret_cast<Sistem*>(system);
    if (!s || !s->widevine)
        return ERROR_INTERFACE_NOT_IMPLEMENTED;
    std::string eroare;
    std::shared_ptr<Modul> m = modulPentru(s, eroare);
    if (!m) {
        jurnal("certificatul serverului: %s", eroare.c_str());
        return ERROR_BUSY_CANNOT_INITIALIZE;
    }
    uint32_t p = m->promisiuneNoua();
    m->acum([&](ApelCdm& c) { c.SetServerCertificate(p, serverCertificate, serverCertificateLength); });
    Promisiune r = m->asteapta(p, 5000);
    return r.bun ? ERROR_NONE : ERROR_FAIL;
}

OpenCDMError opencdm_construct_session(OpenCDMSystem* system, const LicenseType licenseType, const char initDataType[],
    const uint8_t initData[], const uint32_t initDataLength, const uint8_t CDMData[], const uint32_t CDMDataLength,
    OpenCDMSessionCallbacks* callbacks, void* userData, OpenCDMSession** session)
{
    if (session)
        *session = nullptr;
    Sistem* sis = reinterpret_cast<Sistem*>(system);
    if (!sis || !session)
        return ERROR_INVALID_ACCESSOR;
    Sesiune* s = new Sesiune();
    s->sistem = sis;
    s->tip = licenseType;
    if (callbacks)
        s->cb = *callbacks;
    s->user = userData;
    {
        std::lock_guard<std::mutex> l(g_lacat);
        g_sesiuni.push_back(s);
    }
    bool incarca = (!initData || !initDataLength) && CDMData && CDMDataLength;
    OpenCDMError r = ERROR_NONE;
    if (!sis->widevine) {
        r = incarca ? ERROR_INVALID_SESSION : clearKeyConstruieste(s, initDataType, initData, initDataLength);
    } else {
        std::string eroare;
        s->modul = modulPentru(sis, eroare);
        if (!s->modul) {
            jurnal("sesiune Widevine: %s", eroare.c_str());
            r = ERROR_BUSY_CANNOT_INITIALIZE;
        } else {
            cdm::SessionType st = licenseType == Temporary ? cdm::kTemporary : cdm::kPersistentLicense;
            uint32_t p = s->modul->promisiuneNoua();
            if (incarca) {
                // the module announces the keys of a loaded session during LoadSession: the session must be known first
                std::string id(reinterpret_cast<const char*>(CDMData), CDMDataLength);
                s->id = id;
                s->modul->inregistreaza(s);
                s->modul->acum([&](ApelCdm& c) { c.LoadSession(p, st, id.data(), (uint32_t)id.size()); });
            } else {
                cdm::InitDataType it = tipInit(initDataType);
                s->modul->acum([&](ApelCdm& c) { c.CreateSessionAndGenerateRequest(p, st, it, initData, initDataLength); });
            }
            Promisiune pr = s->modul->asteapta(p, 10000);
            if (!pr.bun || (!incarca && pr.sesiune.empty())) {
                jurnal("sesiunea Widevine nu s-a facut: %s", pr.eroare.c_str());
                r = incarca ? ERROR_INVALID_SESSION : ERROR_FAIL;
            } else if (!incarca) {
                s->id = pr.sesiune;
                s->modul->inregistreaza(s);   // the license request of the module goes now to WebKit
            }
        }
    }
    if (r != ERROR_NONE) {
        lasa(s);
        return r;
    }
    if (jurnalLung())
        jurnal("sesiunea %s (%s)", s->id.c_str(), sis->cheie.c_str());
    *session = reinterpret_cast<OpenCDMSession*>(s);
    return ERROR_NONE;
}

OpenCDMError opencdm_destruct_session(OpenCDMSession* session)
{
    if (!session)
        return ERROR_INVALID_ACCESSOR;
    lasa(reinterpret_cast<Sesiune*>(session));
    return ERROR_NONE;
}

OpenCDMSession* opencdm_get_system_session(OpenCDMSystem* system, const uint8_t keyId[], const uint8_t length,
    const uint32_t waitTime)
{
    Sistem* sis = reinterpret_cast<Sistem*>(system);
    Bytes k(keyId, keyId + length);
    std::unique_lock<std::mutex> l(g_lacat);
    auto gaseste = [&]() -> Sesiune* {
        for (Sesiune* s : g_sesiuni) {
            if (s->sistem == sis) {
                auto it = s->stari.find(k);
                if (it != s->stari.end() && it->second == Usable)
                    return s;
            }
        }
        return nullptr;
    };
    Sesiune* s = nullptr;
    g_cheiNoi.wait_for(l, std::chrono::milliseconds(waitTime), [&] { return (s = gaseste()) != nullptr; });
    if (!s)
        return nullptr;
    tine(s);
    return reinterpret_cast<OpenCDMSession*>(s);
}

const char* opencdm_session_id(const OpenCDMSession* session)
{
    const Sesiune* s = reinterpret_cast<const Sesiune*>(session);
    return s ? s->id.c_str() : "";
}

KeyStatus opencdm_session_status(const OpenCDMSession* session, const uint8_t keyId[], const uint8_t length)
{
    const Sesiune* s = reinterpret_cast<const Sesiune*>(session);
    if (!s)
        return InternalError;
    std::lock_guard<std::mutex> l(g_lacat);
    auto it = s->stari.find(Bytes(keyId, keyId + length));
    return it == s->stari.end() ? StatusPending : it->second;
}

OpenCDMError opencdm_session_update(OpenCDMSession* session, const uint8_t keyMessage[], const uint32_t keyLength)
{
    Sesiune* s = reinterpret_cast<Sesiune*>(session);
    if (!s || s->id.empty())
        return ERROR_INVALID_SESSION;
    if (!s->modul)
        return clearKeyActualizeaza(s, keyMessage, keyLength);
    uint32_t p = s->modul->promisiuneFaraAsteptare();
    s->cheiAnuntate = false;
    s->modul->legaActualizare(p, s);   // the answer (keys_updated or error_message) comes from the worker thread
    std::string id = s->id;
    s->modul->acum([&](ApelCdm& c) { c.UpdateSession(p, id.data(), (uint32_t)id.size(), keyMessage, keyLength); });
    // nobody waits for this promise: the callbacks above answer WebKit
    return ERROR_NONE;
}

OpenCDMError opencdm_session_load(OpenCDMSession* session)
{
    Sesiune* s = reinterpret_cast<Sesiune*>(session);
    if (!s || s->id.empty())
        return ERROR_INVALID_SESSION;
    // the session was loaded in opencdm_construct_session (LoadSession); the keys come through the callbacks
    if (s->cb.keys_updated_callback)
        s->cb.keys_updated_callback(manier(s), s->user);
    return ERROR_NONE;
}

OpenCDMError opencdm_session_remove(OpenCDMSession* session)
{
    Sesiune* s = reinterpret_cast<Sesiune*>(session);
    if (!s || s->id.empty())
        return ERROR_INVALID_SESSION;
    if (!s->modul) {
        std::lock_guard<std::mutex> l(g_lacat);
        s->chei.clear();
        for (auto& st : s->stari)
            st.second = Released;
        return ERROR_NONE;
    }
    uint32_t p = s->modul->promisiuneNoua();
    std::string id = s->id;
    s->modul->acum([&](ApelCdm& c) { c.RemoveSession(p, id.data(), (uint32_t)id.size()); });
    return s->modul->asteapta(p, 5000).bun ? ERROR_NONE : ERROR_FAIL;
}

OpenCDMError opencdm_session_close(OpenCDMSession* session)
{
    Sesiune* s = reinterpret_cast<Sesiune*>(session);
    if (!s)
        return ERROR_INVALID_SESSION;
    if (s->modul && !s->id.empty()) {
        uint32_t p = s->modul->promisiuneNoua();
        std::string id = s->id;
        s->modul->acum([&](ApelCdm& c) { c.CloseSession(p, id.data(), (uint32_t)id.size()); });
        s->modul->asteapta(p, 3000);
    }
    std::lock_guard<std::mutex> l(g_lacat);
    s->chei.clear();
    for (auto& st : s->stari)
        st.second = Released;
    return ERROR_NONE;
}

OpenCDMError hds_ocdm_session_decrypt(OpenCDMSession* session, uint8_t* data, uint32_t size, uint32_t scheme,
    const uint8_t keyId[], uint32_t keyIdLength, const uint8_t iv[], uint32_t ivLength, const HdsOcdmSubsample* subsamples,
    uint32_t subsampleCount, uint32_t cryptByteBlock, uint32_t skipByteBlock, int64_t timestampUs)
{
    Sesiune* s = reinterpret_cast<Sesiune*>(session);
    if (!s || !data)
        return ERROR_INVALID_ACCESSOR;
    if (scheme == 0 || !size)
        return ERROR_NONE;
    Bytes kid(keyId, keyId + keyIdLength);
    if (!s->modul) {
        Bytes cheie;
        {
            std::lock_guard<std::mutex> l(g_lacat);
            auto it = s->chei.find(kid);
            if (it == s->chei.end())
                return ERROR_INVALID_ACCESSOR;   // WebKit: NoKey
            cheie = it->second;
        }
        return decripteazaAes(cheie, scheme, data, size, iv, ivLength, subsamples, subsampleCount, cryptByteBlock, skipByteBlock);
    }
    // the module wants an IV of 16 bytes (an IV of 8 is padded with zeros, as browsers do)
    uint8_t iv16[16] = {};
    memcpy(iv16, iv, std::min<uint32_t>(ivLength, 16));
    std::vector<cdm::SubsampleEntry> sub(subsampleCount);
    for (uint32_t i = 0; i < subsampleCount; i++) {
        sub[i].clear_bytes = subsamples[i].clear_bytes;
        sub[i].cipher_bytes = subsamples[i].cipher_bytes;
    }
    cdm::InputBuffer_2 in = {};
    in.data = data;
    in.data_size = size;
    in.encryption_scheme = scheme == 2 ? cdm::EncryptionScheme::kCbcs : cdm::EncryptionScheme::kCenc;
    in.key_id = kid.data();
    in.key_id_size = (uint32_t)kid.size();
    in.iv = iv16;
    in.iv_size = 16;
    in.subsamples = sub.empty() ? nullptr : sub.data();
    in.num_subsamples = (uint32_t)sub.size();
    in.pattern.crypt_byte_block = cryptByteBlock;
    in.pattern.skip_byte_block = skipByteBlock;
    in.timestamp = timestampUs;
    BlocDecriptat out;
    cdm::Status st = cdm::kDecryptError;
    s->modul->acum([&](ApelCdm& c) { st = c.Decrypt(in, &out); });
    if (st == cdm::kNoKey)
        return ERROR_INVALID_ACCESSOR;
    if (st != cdm::kSuccess || !out.b) {
        static std::atomic<int> spuse { 0 };
        if (spuse++ < 5)
            jurnal("Decrypt a dat starea %u (%s)", (unsigned)st,
                st == cdm::kDecryptError ? "decriptarea simpla poate fi refuzata de licenta" : "eroare");
        return ERROR_FAIL;
    }
    if (out.b->Size() != size) {
        jurnal("Decrypt a dat %u octeti in loc de %u", out.b->Size(), size);
        return ERROR_INVALID_DECRYPT_BUFFER;
    }
    memcpy(data, out.b->Data(), size);
    return ERROR_NONE;
}

} // extern "C"
