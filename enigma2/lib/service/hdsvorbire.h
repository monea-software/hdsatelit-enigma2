/* Copyright (C) 2026 moneasoftware.com & hdsatelit.com
 * SPDX-License-Identifier: GPL-2.0-only
 * Passive sink-pad copy. No decoder state changes, no Python on streaming threads. */
#ifndef HDS_VORBIRE_H
#define HDS_VORBIRE_H
#include <gst/gst.h>
#include <mutex>
#include <memory>
#include <vector>
#include <string>
#include <chrono>
#include <atomic>
#include <algorithm>
#include <cstring>

struct HdsVorbireCopie
{
	std::mutex mutex;
	std::vector<unsigned char> bytes;
	std::string codec;
	int rate = 0, channels = 0;
	bool gap = true;
	std::atomic<bool> active{true};
	std::atomic<bool> dropped{false};
	std::chrono::steady_clock::time_point last = std::chrono::steady_clock::now();

	static GstPadProbeReturn copy(GstPad *pad, GstPadProbeInfo *info, gpointer opaque)
	{
		auto &s = **static_cast<std::shared_ptr<HdsVorbireCopie> *>(opaque);
		std::unique_lock<std::mutex> lock(s.mutex, std::try_to_lock);
		if (!lock.owns_lock())
		{
			s.dropped = true;
			return GST_PAD_PROBE_OK;
		}
		if (!s.active)
			return GST_PAD_PROBE_OK;
		if (s.dropped.exchange(false))
		{
			s.bytes.clear(); s.gap = true;
		}
		if (std::chrono::steady_clock::now() - s.last > std::chrono::seconds(1))
		{
			s.bytes.clear();
			s.gap = true;
			return GST_PAD_PROBE_OK;
		}
		if (GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM)
		{
			GstEvent *event = GST_PAD_PROBE_INFO_EVENT(info);
			if (GST_EVENT_TYPE(event) == GST_EVENT_SEGMENT || GST_EVENT_TYPE(event) == GST_EVENT_FLUSH_START ||
				GST_EVENT_TYPE(event) == GST_EVENT_CAPS)
			{
				s.bytes.clear();
				s.gap = true;
			}
			return GST_PAD_PROBE_OK;
		}
		GstBuffer *buffer = GST_PAD_PROBE_INFO_BUFFER(info);
		if (!buffer || gst_buffer_get_size(buffer) > 65536)
		{
			s.bytes.clear(); s.gap = true;
			return GST_PAD_PROBE_OK;
		}
		GstCaps *caps = gst_pad_get_current_caps(pad);
		if (!caps || gst_caps_is_empty(caps))
		{
			if (caps) gst_caps_unref(caps);
			return GST_PAD_PROBE_OK;
		}
		const GstStructure *c = gst_caps_get_structure(caps, 0);
		const char *name = gst_structure_get_name(c);
		std::string codec;
		int aac_profile = 0, aac_freq = -1, aac_channels = 0;
		int rate = 0, channels = 0, version = 0, layer = 0;
		gst_structure_get_int(c, "rate", &rate);
		gst_structure_get_int(c, "channels", &channels);
		if (!strcmp(name, "audio/mpeg"))
		{
			gst_structure_get_int(c, "mpegversion", &version);
			gst_structure_get_int(c, "layer", &layer);
			const char *format = gst_structure_get_string(c, "stream-format");
			if (version == 1 && layer == 2) codec = "mp2";
			else if (version == 1 && layer == 3) codec = "mp3";
			else if (format && !strcmp(format, "adts")) codec = "adts";
			else if (format && !strcmp(format, "loas")) codec = "loas";
			else if (version == 4 && format && !strcmp(format, "raw"))
			{
				const GValue *v = gst_structure_get_value(c, "codec_data");
				GstBuffer *asc = v && GST_VALUE_HOLDS_BUFFER(v) ? gst_value_get_buffer(v) : nullptr;
				unsigned char bytes[16] = {};
				const size_t size = asc ? std::min((size_t)16, gst_buffer_get_size(asc)) : 0;
				if (size >= 2 && gst_buffer_extract(asc, 0, bytes, size) == size)
				{
					aac_profile = bytes[0] >> 3;
					aac_freq = ((bytes[0] & 7) << 1) | (bytes[1] >> 7);
					aac_channels = (bytes[1] >> 3) & 15;
					if (aac_profile == 5 || aac_profile == 29)
					{
						unsigned int pos = 13;
						auto bits = [&](unsigned int n) -> int {
							if (pos + n > size * 8) return -1;
							int v = 0;
							while (n--) { v = (v << 1) | ((bytes[pos / 8] >> (7 - pos % 8)) & 1); ++pos; }
							return v;
						};
						const int extension_rate = bits(4);
						if (extension_rate == 15) bits(24);
						aac_profile = extension_rate >= 0 ? bits(5) : -1;
					}
					if (aac_profile >= 1 && aac_profile <= 4 && aac_freq < 13 && aac_channels >= 1 && aac_channels <= 7)
						codec = "adts";
				}
			}
		}
		else if (!strcmp(name, "audio/x-ac3")) codec = "ac3";
		else if (!strcmp(name, "audio/x-eac3")) codec = "eac3";
		else if (!strcmp(name, "audio/x-raw"))
		{
			const char *format = gst_structure_get_string(c, "format");
			const char *layout = gst_structure_get_string(c, "layout");
			if (format && !strcmp(format, "S16LE") && layout && !strcmp(layout, "interleaved") &&
				rate >= 8000 && rate <= 96000 && channels >= 1 && channels <= 8) codec = "pcm";
		}
		gst_caps_unref(caps);
		if (codec.empty()) return GST_PAD_PROBE_OK;
		if (codec != s.codec || rate != s.rate || channels != s.channels || GST_BUFFER_FLAG_IS_SET(buffer, GST_BUFFER_FLAG_DISCONT))
		{
			s.bytes.clear();
			s.gap = true;
		}
		s.codec = codec; s.rate = rate; s.channels = channels;
		GstMapInfo map;
		if (gst_buffer_map(buffer, &map, GST_MAP_READ))
		{
			const size_t prefix = aac_profile && codec == "adts" ? 7 : 0;
			if ((prefix && map.size + 7 > 8191) || map.size + prefix > 65536)
			{
				gst_buffer_unmap(buffer, &map);
				s.bytes.clear(); s.gap = true;
				return GST_PAD_PROBE_OK;
			}
			if (s.bytes.size() + map.size + prefix > 65536)
			{
				s.bytes.clear();
				s.gap = true;
			}
			if (prefix)
			{
				const size_t n = map.size + 7;
				const unsigned char adts[] = {0xff, 0xf1,
					(unsigned char)(((aac_profile - 1) << 6) | (aac_freq << 2) | (aac_channels >> 2)),
					(unsigned char)(((aac_channels & 3) << 6) | (n >> 11)),
					(unsigned char)(n >> 3), (unsigned char)(((n & 7) << 5) | 0x1f), 0xfc};
				s.bytes.insert(s.bytes.end(), adts, adts + 7);
			}
			s.bytes.insert(s.bytes.end(), map.data, map.data + map.size);
			gst_buffer_unmap(buffer, &map);
		}
		return GST_PAD_PROBE_OK;
	}
	static void release(gpointer p) { delete static_cast<std::shared_ptr<HdsVorbireCopie> *>(p); }
};

struct HdsVorbireTap
{
	GstPad *pad = nullptr;
	gulong probe = 0;
	std::shared_ptr<HdsVorbireCopie> state;
	~HdsVorbireTap() { stop(); }
	void stop()
	{
		if (state)
		{
			state->active = false;
		}
		if (pad)
		{
			gst_pad_remove_probe(pad, probe);
			gst_object_unref(pad);
		}
		pad = nullptr; probe = 0; state.reset();
	}
	PyObject *read(GstElement *playbin)
	{
		if (!pad && playbin)
		{
			GstElement *sink = nullptr;
			g_object_get(G_OBJECT(playbin), "audio-sink", &sink, NULL);
			if (sink)
			{
				pad = gst_element_get_static_pad(sink, "sink");
				gst_object_unref(sink);
			}
			if (pad)
			{
				state = std::make_shared<HdsVorbireCopie>();
				probe = gst_pad_add_probe(pad, (GstPadProbeType)(GST_PAD_PROBE_TYPE_BUFFER | GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM | GST_PAD_PROBE_TYPE_EVENT_FLUSH),
					HdsVorbireCopie::copy, new std::shared_ptr<HdsVorbireCopie>(state), HdsVorbireCopie::release);
			}
		}
		if (!state) return PyDict_New();
		std::unique_lock<std::mutex> lock(state->mutex, std::try_to_lock);
		if (!lock.owns_lock()) return PyDict_New();
		state->last = std::chrono::steady_clock::now();
		PyObject *data = PyBytes_FromStringAndSize(state->bytes.empty() ? "" : (const char *)state->bytes.data(), state->bytes.size());
		if (!data) return nullptr;
		PyObject *d = Py_BuildValue("{s:O,s:s,s:i,s:i,s:i}", "date", data,
			"fel", state->codec.c_str(), "rata", state->rate, "canale", state->channels, "salt", state->gap ? 1 : 0);
		Py_DECREF(data);
		state->bytes.clear(); state->gap = false;
		return d;
	}
};
#endif
