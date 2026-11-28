/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-ocdm: the OpenCDM C interface that WPE WebKit (ENABLE_THUNDER) uses for Encrypted Media Extensions,
 * written for the HD Satelit image. The declarations follow what WebKit 2.54 calls (CDMThunder.cpp,
 * CDMProxyThunder.cpp, CDMOpenCDMTypes.h): the names WebKit uses are kept, the code behind them is ours
 * (libocdm.so, hds-ocdm.cpp): key systems "org.w3.clearkey" (keys handled here) and "com.widevine.alpha"
 * (the Widevine module that the receiver of the user downloads from Google, hosted through the public CDM
 * interface, decryption only, the compressed frames go on to the board decoder).
 */
#ifndef HDS_OPEN_CDM_H
#define HDS_OPEN_CDM_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HDS_OCDM_EXPORT __attribute__((visibility("default")))

struct OpenCDMSystem;
struct OpenCDMSession;

typedef enum {
    ERROR_NONE = 0,
    ERROR_UNKNOWN = 1,
    ERROR_MORE_DATA_AVAILBALE = 2,
    ERROR_INTERFACE_NOT_IMPLEMENTED = 3,
    ERROR_BUFFER_TOO_SMALL = 4,
    ERROR_INVALID_ACCESSOR = 0x80000001,
    ERROR_KEYSYSTEM_NOT_SUPPORTED = 0x80000002,
    ERROR_INVALID_SESSION = 0x80000003,
    ERROR_INVALID_DECRYPT_BUFFER = 0x80000004,
    ERROR_OUT_OF_MEMORY = 0x80000005,
    ERROR_BUSY_CANNOT_INITIALIZE = 0x80000006,
    ERROR_FAIL = 0x80004005
} OpenCDMError;

typedef enum {
    Usable = 0,
    Expired,
    Released,
    OutputRestricted,
    OutputRestrictedHDCP22,
    OutputDownscaled,
    StatusPending,
    InternalError,
    HWError
} KeyStatus;

typedef enum {
    Temporary = 0,
    PersistentUsageRecord,
    PersistentLicense
} LicenseType;

/* The callbacks may come from any thread (WebKit moves them to its main thread). The challenge is sent as
 * "<message type digit>:Type:<payload>" (0 license request, 1 renewal, 2 release, 3 individualization). */
typedef struct {
    void (*process_challenge_callback)(struct OpenCDMSession* session, void* userData, const char url[],
        const uint8_t challenge[], const uint16_t challengeLength);
    void (*key_update_callback)(struct OpenCDMSession* session, void* userData, const uint8_t keyId[],
        const uint8_t length);
    void (*error_message_callback)(struct OpenCDMSession* session, void* userData, const char message[]);
    void (*keys_updated_callback)(const struct OpenCDMSession* session, void* userData);
} OpenCDMSessionCallbacks;

/* ERROR_NONE when the key system (and, when given, the content type such as video/mp4; codecs="avc1.4d401f")
 * can be used. */
HDS_OCDM_EXPORT OpenCDMError opencdm_is_type_supported(const char keySystem[], const char mimeType[]);

HDS_OCDM_EXPORT struct OpenCDMSystem* opencdm_create_system(const char keySystem[]);
HDS_OCDM_EXPORT OpenCDMError opencdm_destruct_system(struct OpenCDMSystem* system);
HDS_OCDM_EXPORT bool opencdm_system_supports_server_certificate(struct OpenCDMSystem* system);
HDS_OCDM_EXPORT OpenCDMError opencdm_system_set_server_certificate(struct OpenCDMSystem* system,
    const uint8_t serverCertificate[], const uint32_t serverCertificateLength);

/* A new session (initData) or, for a persistent session to load, the session id in CDMData. The session
 * returned holds one reference; opencdm_destruct_session drops it. */
HDS_OCDM_EXPORT OpenCDMError opencdm_construct_session(struct OpenCDMSystem* system, const LicenseType licenseType,
    const char initDataType[], const uint8_t initData[], const uint32_t initDataLength, const uint8_t CDMData[],
    const uint32_t CDMDataLength, OpenCDMSessionCallbacks* callbacks, void* userData, struct OpenCDMSession** session);
HDS_OCDM_EXPORT OpenCDMError opencdm_destruct_session(struct OpenCDMSession* session);

/* The session that holds the key, with one more reference (released with opencdm_destruct_session), or NULL
 * after waitTime milliseconds. */
HDS_OCDM_EXPORT struct OpenCDMSession* opencdm_get_system_session(struct OpenCDMSystem* system, const uint8_t keyId[],
    const uint8_t length, const uint32_t waitTime);

HDS_OCDM_EXPORT const char* opencdm_session_id(const struct OpenCDMSession* session);
HDS_OCDM_EXPORT KeyStatus opencdm_session_status(const struct OpenCDMSession* session, const uint8_t keyId[],
    const uint8_t length);
HDS_OCDM_EXPORT OpenCDMError opencdm_session_update(struct OpenCDMSession* session, const uint8_t keyMessage[],
    const uint32_t keyLength);
HDS_OCDM_EXPORT OpenCDMError opencdm_session_load(struct OpenCDMSession* session);
HDS_OCDM_EXPORT OpenCDMError opencdm_session_remove(struct OpenCDMSession* session);
HDS_OCDM_EXPORT OpenCDMError opencdm_session_close(struct OpenCDMSession* session);

/* Decryption of one sample in place (no GStreamer types: used by open_cdm_adapter.h and by the tests).
 * scheme: 0 clear, 1 cenc (AES-CTR), 2 cbcs (AES-CBC with pattern). subsamples: pairs (clear, cipher) in
 * host order, or NULL for a fully encrypted sample. */
typedef struct {
    uint32_t clear_bytes;
    uint32_t cipher_bytes;
} HdsOcdmSubsample;

HDS_OCDM_EXPORT OpenCDMError hds_ocdm_session_decrypt(struct OpenCDMSession* session, uint8_t* data, uint32_t size,
    uint32_t scheme, const uint8_t keyId[], uint32_t keyIdLength, const uint8_t iv[], uint32_t ivLength,
    const HdsOcdmSubsample* subsamples, uint32_t subsampleCount, uint32_t cryptByteBlock, uint32_t skipByteBlock,
    int64_t timestampUs);

#ifdef __cplusplus
}
#endif

#endif
