/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-ocdm: the GStreamer side of the OpenCDM interface used by WPE WebKit (CDMProxyThunder.cpp).
 * opencdm_gstreamer_session_decrypt_buffer reads the GstProtectionMeta that qtdemux / matroskademux put on the
 * buffer (kid, iv or constant_iv, subsamples, cipher-mode cenc / cbcs, crypt_byte_block, skip_byte_block) and
 * decrypts the buffer in place; the frame stays compressed for the board decoder.
 * No GStreamer include here: WebKit checks the symbol with check_cxx_symbol_exists, which gives the compiler only the
 * library, not the GStreamer include paths; with <gst/gst.h> the check would fail quietly and WebKit would take the
 * old form (without the scheme). The two GStreamer types are declared as GStreamer declares them.
 */
#ifndef HDS_OPEN_CDM_ADAPTER_H
#define HDS_OPEN_CDM_ADAPTER_H

#include "open_cdm.h"

typedef struct _GstBuffer GstBuffer;
typedef struct _GstCaps GstCaps;

#ifdef __cplusplus
extern "C" {
#endif

HDS_OCDM_EXPORT OpenCDMError opencdm_gstreamer_session_decrypt_buffer(struct OpenCDMSession* session, GstBuffer* buffer,
    GstCaps* caps);

/* Older form (no scheme: cenc): subSample holds big-endian (uint16 clear, uint32 cipher) pairs. */
HDS_OCDM_EXPORT OpenCDMError opencdm_gstreamer_session_decrypt(struct OpenCDMSession* session, GstBuffer* buffer,
    GstBuffer* subSample, const uint32_t subSampleCount, GstBuffer* IV, GstBuffer* keyID, uint32_t initWithLast15);

#ifdef __cplusplus
}
#endif

#endif
