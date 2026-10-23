# Modificat de moneasoftware.com si hdsatelit.com, 2026
AM_CPPFLAGS = \
	-I$(top_srcdir) \
	-I$(top_srcdir)/include \
	-include Python.h \
	-include $(top_builddir)/enigma2_config.h

AM_CXXFLAGS = \
	$(GSTREAMER_CFLAGS)

noinst_LIBRARIES = libenigma_service.a

libenigma_service_a_SOURCES = \
	event.cpp \
	listboxservice.cpp \
	service.cpp \
	servicedvb.cpp \
	hdsegalizator.cpp \
	hdsfluxhttp.cpp \
	servicedvbrecord.cpp \
	servicefs.cpp \
	servicem2ts.cpp

serviceincludedir = $(pkgincludedir)/lib/service
serviceinclude_HEADERS = \
	event.h \
	iservice.h \
	listboxservice.h \
	service.h \
	servicedvb.h \
	hdsegalizator.h \
	hdsfluxhttp.h \
	hdsegalizator_dsp.h \
	hdsegalizator_flux.h \
	hdssubtitrareceas.h \
	servicedvbrecord.h \
	servicefs.h \
	servicem2ts.h

if HAVE_GSTREAMER
libenigma_service_a_SOURCES += \
	hdssubimagini.cpp \
	servicemp3.cpp
serviceinclude_HEADERS += \
	hdssubimagini.h \
	servicemp3.h
endif
