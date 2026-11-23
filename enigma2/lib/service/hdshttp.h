/* Copyright (C) 2026 moneasoftware.com & hdsatelit.com
 * SPDX-License-Identifier: GPL-2.0-only
 * Per-playback HTTP identity, also available to detached HLS downloaders.
 */
#ifndef HDS_HTTP_H
#define HDS_HTTP_H
#include <gst/gst.h>
#include <string>
#include <cstring>
#include "hdshttporigin.h"

namespace hdshttp {
static inline bool numeValid(const std::string &s)
{
	if (s.empty() || s.size() > 128 || !g_ascii_strcasecmp(s.c_str(), "hds-origin")) return false;
	for (unsigned char c : s)
		if (!g_ascii_isalnum(c) && !strchr("!#$%&'*+-.^_`|~", c)) return false;
	/* Transport framing belongs to the HTTP implementation. */
	for (const char *n : {"Host", "Content-Length", "Connection", "Transfer-Encoding", "Range"})
		if (!g_ascii_strcasecmp(s.c_str(), n)) return false;
	return true;
}

static inline bool valoareValida(const std::string &s)
{
	if (s.size() > 16384) return false;
	for (unsigned char c : s) if (c < 32 || c == 127) return false;
	return true;
}

static inline GstContext *pregateste(std::string &uri, const std::string &agent)
{
	if (uri.compare(0, 7, "http://") && uri.compare(0, 8, "https://")) return NULL;
	GstContext *context = gst_context_new("hds.http.headers", TRUE);
	GstStructure *headers = gst_context_writable_structure(context);
	hds_http_set_origin(headers, uri.substr(0, uri.find('#')).c_str());
	if (valoareValida(agent)) gst_structure_set(headers, "User-Agent", G_TYPE_STRING, agent.c_str(), NULL);
	size_t hash = uri.find('#');
	/* Ordinary URL fragments retain their existing meaning. */
	if (hash == std::string::npos || uri.find('=', hash) == std::string::npos) return context;
	std::string fields = uri.substr(hash + 1);
	uri.erase(hash);
	for (size_t pos = 0; pos < fields.size(); )
	{
		size_t end = fields.find('&', pos);
		if (end == std::string::npos) end = fields.size();
		std::string part = fields.substr(pos, end - pos);
		size_t eq = part.find('=');
		if (eq != std::string::npos)
		{
			gchar *key = g_uri_unescape_string(part.substr(0, eq).c_str(), NULL);
			gchar *value = g_uri_unescape_string(part.substr(eq + 1).c_str(), NULL);
			if (key && value && numeValid(key) && valoareValida(value))
			{
				/* Collapse case variants, so an override never creates a second UA. */
				for (int i = gst_structure_n_fields(headers) - 1; i >= 0; --i)
				{
					const char *old = gst_structure_nth_field_name(headers, i);
					if (!g_ascii_strcasecmp(old, key)) gst_structure_remove_field(headers, old);
				}
				gst_structure_set(headers, key, G_TYPE_STRING, value, NULL);
			}
			g_free(key);
			g_free(value);
		}
		pos = end + 1;
	}
	return context;
}

static inline void aplica(GstElement *element, GstContext *context)
{
	if (!context) return;
	const GstStructure *headers = gst_context_get_structure(context);
	GObjectClass *klass = G_OBJECT_GET_CLASS(element);
	GParamSpec *agent = g_object_class_find_property(klass, "user-agent");
	GParamSpec *extraSpec = g_object_class_find_property(klass, "extra-headers");
	bool areAgent = agent && G_PARAM_SPEC_VALUE_TYPE(agent) == G_TYPE_STRING && (agent->flags & G_PARAM_WRITABLE);
	bool areExtra = extraSpec && G_PARAM_SPEC_VALUE_TYPE(extraSpec) == GST_TYPE_STRUCTURE && (extraSpec->flags & G_PARAM_WRITABLE);
	if (!areAgent && !areExtra) return;
	GstStructure *extra = NULL;
	if (areExtra && (extraSpec->flags & G_PARAM_READABLE))
		g_object_get(element, "extra-headers", &extra, NULL);
	if (!extra) extra = gst_structure_new_empty("headers");
	gchar *uri = GST_IS_URI_HANDLER(element) ? gst_uri_handler_get_uri(GST_URI_HANDLER(element)) : NULL;
	bool allowed = hds_http_origin_matches(headers, uri);
	g_free(uri);
	for (int i = 0; i < gst_structure_n_fields(headers); ++i)
	{
		const char *key = gst_structure_nth_field_name(headers, i);
		const char *value = gst_structure_get_string(headers, key);
		if (!value) continue;
		if (!g_ascii_strcasecmp(key, "User-Agent") && areAgent)
			g_object_set(element, "user-agent", value, NULL);
		else if (allowed || !g_ascii_strcasecmp(key, "User-Agent"))
			gst_structure_set(extra, key, G_TYPE_STRING, value, NULL);
		else gst_structure_remove_field(extra, key);
	}
	if (areExtra)
		g_object_set(element, "extra-headers", extra, NULL);
	gst_structure_free(extra);
}

static inline void sursa(GstElement *player, GstElement *source, gpointer)
{
	GstContext *context = gst_element_get_context(player, "hds.http.headers");
	aplica(source, context);
	if (context) gst_context_unref(context);
}
}
#endif
