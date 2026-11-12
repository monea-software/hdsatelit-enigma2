AM_CPPFLAGS = \
	-I$(top_srcdir) \
	-I$(top_srcdir)/include \
	-include Python.h \
	-include $(top_builddir)/enigma2_config.h

noinst_LIBRARIES = libenigma_dvb_ci.a

# CI+ (aes_xcbc_mac, descrambler, dvbci_ccmgr*, host_ctrl, hlcmgr, cam_upgrade, app_mmi, operatorprofile): din
# sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4; cer libcrypto (configure.ac)
libenigma_dvb_ci_a_SOURCES = \
	aes_xcbc_mac.cpp \
	descrambler.cpp \
	dvbci.cpp \
	dvbci_app_mmi.cpp \
	dvbci_appmgr.cpp \
	dvbci_cam_upgrade.cpp \
	dvbci_camgr.cpp \
	dvbci_ccmgr.cpp \
	dvbci_ccmgr_helper.cpp \
	dvbci_datetimemgr.cpp \
	dvbci_hlcmgr.cpp \
	dvbci_host_ctrl.cpp \
	dvbci_mmi.cpp \
	dvbci_operatorprofile.cpp \
	dvbci_resmgr.cpp \
	dvbci_session.cpp \
	dvbci_ui.cpp

dvbciincludedir = $(pkgincludedir)/lib/dvb_ci
dvbciinclude_HEADERS = \
	aes_xcbc_mac.h \
	descrambler.h \
	dvbci.h \
	dvbci_app_mmi.h \
	dvbci_appmgr.h \
	dvbci_cam_upgrade.h \
	dvbci_camgr.h \
	dvbci_ccmgr.h \
	dvbci_ccmgr_helper.h \
	dvbci_datetimemgr.h \
	dvbci_hds_compat.h \
	dvbci_hlcmgr.h \
	dvbci_host_ctrl.h \
	dvbci_mmi.h \
	dvbci_operatorprofile.h \
	dvbci_resmgr.h \
	dvbci_session.h \
	dvbci_ui.h \
	hdsdatetimeci.h
