/* Copyright (C) 2026 moneasoftware.com & hdsatelit.com
 * SPDX-License-Identifier: LGPL-2.0-or-later
 * Private headers are scoped to the original HTTP scheme, host and port.
 */
#ifndef HDS_HTTP_ORIGIN_H
#define HDS_HTTP_ORIGIN_H
#include <gst/gst.h>

static inline GUri *hds_http_parse_origin(const gchar *uri)
{
  GUri *parsed = uri ? g_uri_parse(uri, G_URI_FLAGS_NONE, NULL) : NULL;
  const gchar *scheme = parsed ? g_uri_get_scheme(parsed) : NULL;
  const gchar *host = parsed ? g_uri_get_host(parsed) : NULL;
  if (!scheme || !host || !*host ||
      (g_ascii_strcasecmp(scheme, "http") && g_ascii_strcasecmp(scheme, "https"))) {
    if (parsed) g_uri_unref(parsed);
    return NULL;
  }
  return parsed;
}

static inline gint hds_http_origin_port(GUri *uri)
{
  gint port = g_uri_get_port(uri);
  return port < 0 ? (g_ascii_strcasecmp(g_uri_get_scheme(uri), "https") ? 80 : 443) : port;
}

static inline void hds_http_set_origin(GstStructure *headers, const gchar *uri)
{
  GUri *parsed = hds_http_parse_origin(uri);
  if (!parsed) return;
  GstStructure *origin = gst_structure_new("origin",
      "scheme", G_TYPE_STRING, g_uri_get_scheme(parsed),
      "host", G_TYPE_STRING, g_uri_get_host(parsed),
      "port", G_TYPE_INT, hds_http_origin_port(parsed), NULL);
  gst_structure_set(headers, "hds-origin", GST_TYPE_STRUCTURE, origin, NULL);
  gst_structure_free(origin);
  g_uri_unref(parsed);
}

static inline gboolean hds_http_origin_matches(const GstStructure *headers, const gchar *uri)
{
  const GValue *value = gst_structure_get_value(headers, "hds-origin");
  const GstStructure *origin = value && GST_VALUE_HOLDS_STRUCTURE(value) ?
      gst_value_get_structure(value) : NULL;
  GUri *parsed = hds_http_parse_origin(uri);
  const gchar *scheme = origin ? gst_structure_get_string(origin, "scheme") : NULL;
  const gchar *host = origin ? gst_structure_get_string(origin, "host") : NULL;
  gint port = -1;
  gboolean allowed = parsed && scheme && host &&
      gst_structure_get_int(origin, "port", &port) &&
      !g_ascii_strcasecmp(scheme, g_uri_get_scheme(parsed)) &&
      !g_ascii_strcasecmp(host, g_uri_get_host(parsed)) &&
      port == hds_http_origin_port(parsed);
  if (parsed) g_uri_unref(parsed);
  return allowed;
}
#endif
