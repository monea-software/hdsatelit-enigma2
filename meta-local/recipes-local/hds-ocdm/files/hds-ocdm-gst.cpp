/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-ocdm: the GStreamer side (open_cdm_adapter.h). WebKit (CDMProxyThunder.cpp) hands one encrypted sample with
 * its GstProtectionMeta (put by qtdemux / matroskademux; WebKit removes it only after the decryption) and the
 * caps; the sample is decrypted in place and stays compressed, so the board decoder (dvbvideosink /
 * dvbaudiosink) gets it as it gets the clear films of YouTube.
 * Fields of the meta (GStreamer qtdemux): "kid" (GstBuffer, 16 bytes), "iv_size" + "iv" (GstBuffer) or
 * for cbcs "constant_iv_size" with the constant IV in "iv" (qtdemux), "subsample_count" + "subsamples" (GstBuffer of big-endian pairs:
 * uint16 clear bytes, uint32 encrypted bytes), "cipher-mode" ("cenc" / "cbcs" / ...), "crypt_byte_block",
 * "skip_byte_block", "encrypted" (FALSE = clear sample).
 */
#include <gst/gst.h>

#include "open_cdm_adapter.h"

#include <cstdio>
#include <cstring>
#include <vector>

namespace {

bool citesteBufer(const GstStructure* s, const char* nume, std::vector<uint8_t>& out)
{
    const GValue* v = gst_structure_get_value(s, nume);
    if (!v || !GST_VALUE_HOLDS_BUFFER(v))
        return false;
    GstBuffer* b = gst_value_get_buffer(v);
    GstMapInfo m;
    if (!b || !gst_buffer_map(b, &m, GST_MAP_READ))
        return false;
    out.assign(m.data, m.data + m.size);
    gst_buffer_unmap(b, &m);
    return true;
}

bool subesantioane(const std::vector<uint8_t>& raw, unsigned n, std::vector<HdsOcdmSubsample>& out)
{
    if (raw.size() < (size_t)n * 6)
        return false;
    out.resize(n);
    for (unsigned i = 0; i < n; i++) {
        const uint8_t* p = raw.data() + i * 6;
        out[i].clear_bytes = ((uint32_t)p[0] << 8) | p[1];
        out[i].cipher_bytes = ((uint32_t)p[2] << 24) | ((uint32_t)p[3] << 16) | ((uint32_t)p[4] << 8) | p[5];
    }
    return true;
}

OpenCDMError decripteaza(OpenCDMSession* session, GstBuffer* buffer, uint32_t schema, const std::vector<uint8_t>& kid,
    const std::vector<uint8_t>& iv, const std::vector<HdsOcdmSubsample>& sub, uint32_t crypt, uint32_t skip)
{
    GstMapInfo m;
    if (!gst_buffer_map(buffer, &m, GST_MAP_READWRITE))
        return ERROR_INVALID_DECRYPT_BUFFER;
    int64_t ts = GST_BUFFER_PTS_IS_VALID(buffer) ? (int64_t)(GST_BUFFER_PTS(buffer) / 1000) : 0;
    OpenCDMError r = hds_ocdm_session_decrypt(session, m.data, (uint32_t)m.size, schema, kid.data(), (uint32_t)kid.size(),
        iv.data(), (uint32_t)iv.size(), sub.empty() ? nullptr : sub.data(), (uint32_t)sub.size(), crypt, skip, ts);
    gst_buffer_unmap(buffer, &m);
    return r;
}

} // namespace

extern "C" {

OpenCDMError opencdm_gstreamer_session_decrypt_buffer(OpenCDMSession* session, GstBuffer* buffer, GstCaps*)
{
    if (!session || !buffer)
        return ERROR_INVALID_ACCESSOR;
    GstProtectionMeta* meta = reinterpret_cast<GstProtectionMeta*>(gst_buffer_get_protection_meta(buffer));
    if (!meta || !meta->info)
        return ERROR_NONE;   // clear sample
    const GstStructure* s = meta->info;
    gboolean criptat = TRUE;
    if (gst_structure_get_boolean(s, "encrypted", &criptat) && !criptat)
        return ERROR_NONE;
    uint32_t schema = 1;
    const char* mod = gst_structure_get_string(s, "cipher-mode");
    if (mod && !g_ascii_strcasecmp(mod, "cbcs"))
        schema = 2;
    else if (mod && g_ascii_strcasecmp(mod, "cenc")) {
        fprintf(stderr, "hds-ocdm: schema de criptare necunoscuta: %s\n", mod);
        return ERROR_INTERFACE_NOT_IMPLEMENTED;
    }
    std::vector<uint8_t> kid, iv, raw;
    citesteBufer(s, "kid", kid);
    // qtdemux writes the constant IV of cbcs in "iv" too (with constant_iv_size); "constant_iv" only as a fallback
    if (!citesteBufer(s, "iv", iv) || iv.empty())
        citesteBufer(s, "constant_iv", iv);
    unsigned n = 0;
    std::vector<HdsOcdmSubsample> sub;
    if (gst_structure_get_uint(s, "subsample_count", &n) && n) {
        if (!citesteBufer(s, "subsamples", raw) || !subesantioane(raw, n, sub))
            return ERROR_INVALID_DECRYPT_BUFFER;
    }
    unsigned crypt = 0, skip = 0;
    gst_structure_get_uint(s, "crypt_byte_block", &crypt);
    gst_structure_get_uint(s, "skip_byte_block", &skip);
    if (kid.empty() || iv.empty())
        return ERROR_INVALID_DECRYPT_BUFFER;
    return decripteaza(session, buffer, schema, kid, iv, sub, crypt, skip);
}

OpenCDMError opencdm_gstreamer_session_decrypt(OpenCDMSession* session, GstBuffer* buffer, GstBuffer* subSample,
    const uint32_t subSampleCount, GstBuffer* IV, GstBuffer* keyID, uint32_t)
{
    if (!session || !buffer || !IV || !keyID)
        return ERROR_INVALID_ACCESSOR;
    // the meta (still on the buffer) knows the scheme (cbcs): the same path as the new form
    if (gst_buffer_get_protection_meta(buffer))
        return opencdm_gstreamer_session_decrypt_buffer(session, buffer, nullptr);
    std::vector<uint8_t> kid, iv, raw;
    GstMapInfo m;
    if (gst_buffer_map(keyID, &m, GST_MAP_READ)) {
        kid.assign(m.data, m.data + m.size);
        gst_buffer_unmap(keyID, &m);
    }
    if (gst_buffer_map(IV, &m, GST_MAP_READ)) {
        iv.assign(m.data, m.data + m.size);
        gst_buffer_unmap(IV, &m);
    }
    std::vector<HdsOcdmSubsample> sub;
    if (subSample && subSampleCount && gst_buffer_map(subSample, &m, GST_MAP_READ)) {
        raw.assign(m.data, m.data + m.size);
        gst_buffer_unmap(subSample, &m);
        if (!subesantioane(raw, subSampleCount, sub))
            return ERROR_INVALID_DECRYPT_BUFFER;
    }
    return decripteaza(session, buffer, 1, kid, iv, sub, 0, 0);
}

} // extern "C"
