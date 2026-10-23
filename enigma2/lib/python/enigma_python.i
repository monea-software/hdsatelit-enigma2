/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
/*
  NOTE: you have two options when adding classes so that
  they are callable *from* python.
  
   - either you %include the header file
   - or you re-declare it
   
  In both cases, you must #include the required
  header file (i.e. the header file itself), otherwise
  enigma_python_wrap.cxx won't build.
  
	In case you import the whole header file,
	please make sure that no unimportant stuff
	is wrapped, as this makes the wrapper stuff
	much more complex and it can probably break 
	very easily because of missing typemaps etc.
	
	you could make use of dizzy macros to ensure
	that some stuff is left out when parsed as SWIG
	definitions, but be sure to not modify the binary 
	representation. DON'T USE #ifdef SWIG_COMPILE
	for leaving out stuff (unless you *really* know
	what you are doing,of course!). you WILL break it.
		
	The better way (with more work) is to re-declare
	the class. It won't be compiled, so you can
	leave out stuff as you like.



Oh, things like "operator= is private in this context" etc.
is usually caused by not marking PSignals as immutable. 
*/

%module enigma
%{

#define SWIG_COMPILE
#include <lib/base/ebase.h>
#include <lib/base/smartptr.h>
#include <lib/base/eenv.h>
#include <lib/base/eerror.h>
#include <lib/base/etpm.h>
#include <lib/base/nconfig.h>
#include <lib/base/message.h>
#include <lib/driver/rc.h>
#include <lib/driver/rcmapper.h>
#include <lib/service/event.h>
#include <lib/service/iservice.h>
#include <lib/service/service.h>
#include <lib/service/servicedvb.h>
#include <lib/gdi/fb.h>
#include <lib/gdi/font.h>
#include <lib/gdi/gpixmap.h>
#include <lib/gdi/gmaindc.h>
#include <lib/gui/ewidget.h>
#include <lib/gui/elabel.h>
#include <lib/gui/einput.h>
#include <lib/gui/einputstring.h>
#include <lib/gui/einputnumber.h>
#include <lib/gui/epixmap.h>
#include <lib/gui/ebutton.h>
#include <lib/gui/ewindow.h>
#include <lib/gui/ewidgetdesktop.h>
#include <lib/gui/ewindowstyle.h>
#include <lib/gui/ewindowstyleskinned.h>
#include <lib/gui/ewidgetanimation.h>
#include <lib/gui/eslider.h>
#include <lib/gui/epositiongauge.h>
#include <lib/gui/evideo.h>
#include <lib/gui/ecanvas.h>
#include <lib/python/connections.h>
#include <lib/gui/elistbox.h>
#include <lib/gui/elistboxcontent.h>
#include <lib/gui/esubtitle.h>
#include <lib/gui/ehdsteletext.h>
#include <lib/service/listboxservice.h>
#include <lib/nav/pcore.h>
#include <lib/actions/action.h>
#include <lib/gdi/gfont.h>
#include <lib/gdi/emvi.h>
#include <lib/gdi/ecranpornire.h>
#include <lib/gdi/epng.h>
#include <lib/dvb/db.h>
#include <lib/dvb/frontendparms.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/frontend.h>
#include <lib/dvb/volume.h>
#include <lib/dvb/sec.h>
#include <lib/dvb/epgcache.h>
#include <lib/dvb/dvbtime.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb/hdsspectru.h>
#include <lib/dvb/hdsteletext.h>
#include <lib/service/hdsegalizator.h>
#include <lib/components/scan.h>
#include <lib/components/file_eraser.h>
#include <lib/driver/avswitch.h>
#include <lib/driver/rfmod.h>
#include <lib/driver/misc_options.h>
#include <lib/driver/etimezone.h>
#include <lib/gdi/lcd.h>
#include <lib/mmi/mmi_ui.h>
#include <lib/dvb_ci/dvbci.h>
#include <lib/dvb_ci/dvbci_ui.h>
#include <lib/python/python.h>
#include <lib/gdi/picload.h>
%}

%feature("ref")   iObject "$this->AddRef(); /* eDebug(\"AddRef (%s:%d)!\", __FILE__, __LINE__); */ "
%feature("unref") iObject "$this->Release(); /* eDebug(\"Release! %s:%d\", __FILE__, __LINE__); */ "

/* this magic allows smartpointer to be used as OUTPUT arguments, i.e. call-by-reference-styled return value. */

/* output arguments: SWIG 4.3 removed t_output_helper and gave SWIG_Python_AppendOutput an is_void argument */
%fragment("hds_append_output","header") %{
#if defined(SWIG_VERSION) && SWIG_VERSION >= 0x040300
#define hds_append_output(result, obj) SWIG_Python_AppendOutput(result, obj, 1)
#else
#define hds_append_output(result, obj) SWIG_Python_AppendOutput(result, obj)
#endif
%}

%define %typemap_output_simple(Type)
 %typemap(in,numinputs=0) Type *OUTPUT ($*1_ltype temp),
              Type &OUTPUT ($*1_ltype temp)
   "$1 = new Type;";
 %fragment("t_out_helper"{Type},"header",
     fragment="hds_append_output") {}
 %typemap(argout,fragment="t_out_helper"{Type}) Type *OUTPUT, Type &OUTPUT
   "$result = hds_append_output($result, (SWIG_NewPointerObj((void*)($1), $1_descriptor, 1)));"
%enddef

%define %typemap_output_ptr(Type)
 %typemap(in,numinputs=0) Type *OUTPUT ($*1_ltype temp),
              Type &OUTPUT ($*1_ltype temp)
   "$1 = new Type;";
 %fragment("t_out_helper"{Type},"header",
     fragment="hds_append_output") {}
 %typemap(argout,fragment="t_out_helper"{Type}) Type *OUTPUT, Type &OUTPUT
		// generate None if smartpointer is NULL
   "$result = hds_append_output($result, ((*$1) ? SWIG_NewPointerObj((void*)($1), $1_descriptor, 1) : (delete $1, Py_INCREF(Py_None), Py_None)));"
%enddef


/* str -> std::string, for every std::string argument (eLabel.setText, eWindow.setTitle, eServiceReference,
   eEnv.resolve ...). SWIG's own version (typemaps/std_strings.swg) fails on a str that cannot be encoded as UTF-8:
   a file name whose bytes are not UTF-8 (a FAT stick, a Latin-1 name) comes with lone surrogates both from
   os.listdir and from C++ (SWIG_FromCharPtrAndSize decodes with "surrogateescape"). SWIG 4.2 then looked up the
   std::string type with the UnicodeEncodeError still set, got a NULL module and stopped enigma2 (SIGSEGV); SWIG 4.3
   clears the error but raises TypeError, so the text is not shown and the screen fails to open. Here a str always
   converts:
   - valid UTF-8 as before (the UTF-8 buffer kept by the str, an embedded '\0' included);
   - lone surrogates U+DC80..U+DCFF back to the original bytes ("surrogateescape", the inverse of what SWIG does from
     C++ to Python), so a path reaches C++ exactly as it is on disk and the file can still be opened; on screen
     eTextPara::renderString (lib/gdi/font.cpp) draws bytes that are not UTF-8 as Latin-1;
   - a str with any other lone surrogate (not from an undecodable byte) through "replace": every surrogate in it
     becomes '?'.
   Anything that is not a str is handled as in SWIG (a wrapped std::string or TypeError), looked up with no Python
   error set. No path returns with a Python error set. Defined before %include "std_string.i": SWIG keeps the first
   definition of a fragment (checked with SWIG 4.2.0 on the PC and 4.3.1 in OE). */
%fragment(SWIG_AsPtr_frag(std::string), "header", fragment="<string>") %{
SWIGINTERN int
SWIG_AsPtr_std_string(PyObject *obj, std::string **val)
{
	if (PyUnicode_Check(obj))
	{
		Py_ssize_t len = 0;
		const char *utf8 = PyUnicode_AsUTF8AndSize(obj, &len);
		if (utf8)
		{
			if (val)
				*val = new std::string(utf8, (size_t)len);
			return SWIG_NEWOBJ;
		}
		PyErr_Clear();
		PyObject *bytes = PyUnicode_AsEncodedString(obj, "utf-8", "surrogateescape");
		if (!bytes)
		{
			PyErr_Clear();
			bytes = PyUnicode_AsEncodedString(obj, "utf-8", "replace");
		}
		int res = SWIG_TypeError;
		if (bytes)
		{
			char *data = 0;
			Py_ssize_t size = 0;
			if (PyBytes_AsStringAndSize(bytes, &data, &size) == 0)
			{
				if (val)
					*val = new std::string(data, (size_t)size);
				res = SWIG_NEWOBJ;
			}
			Py_DECREF(bytes);
		}
		if (res != SWIG_NEWOBJ)
			PyErr_Clear();
		return res;
	}
	PyErr_Clear();
	static swig_type_info *descriptor = SWIG_TypeQuery("std::string *");
	if (descriptor)
	{
		std::string *vptr;
		int res = SWIG_ConvertPtr(obj, (void**)&vptr, descriptor, 0);
		if (SWIG_IsOK(res) && val)
			*val = vptr;
		return res;
	}
	return SWIG_ERROR;
}
%}

#define DEBUG
typedef long time_t;
%include "typemaps.i"
%include "std_string.i"

/* str -> char * / const char *, for every char * argument (iRecordableService.prepare, ePicLoad.startDecode,
   ePicLoad.getThumbnail, loadPNG/loadJPG/savePNG, ePixmap.setPixmapFromFile, eBackgroundFileEraser.erase,
   iTimeshiftService.setNextPlaybackFile, eCanvas.writeText, eDVBDB.loadServicelist/saveServicelist,
   eEPGCache.setCacheFile, addFont, ePythonOutput ...). SWIG's own SWIG_AsCharPtrAndSize (python/pystrings.swg)
   cannot be replaced by a %fragment here, because python.swg loads pystrings.swg before this file; so the
   typemaps themselves are replaced instead (a typemap declared later wins). SWIG's version calls
   PyUnicode_AsUTF8AndSize and, for a str that cannot be encoded as UTF-8 (a file name whose bytes are not UTF-8,
   a title broken by the broadcaster; both arrive with lone surrogates, because SWIG_FromCharPtrAndSize decodes
   from C++ with "surrogateescape"), returns SWIG_TypeError with the UnicodeEncodeError still set: the recording
   does not start, the picture is not loaded, the file is not erased, and the leftover error shows up later as a
   SystemError. Here:
   - valid UTF-8 exactly as before: the pointer into the UTF-8 buffer owned by the str, alloc = SWIG_OLDOBJ,
     no copy at all (so the generated code and the behaviour are unchanged for every normal string);
   - otherwise the bytes are rebuilt with "surrogateescape" (the inverse of what SWIG does from C++ to Python),
     or with "replace" for a surrogate that does not come from a byte, into a NUL terminated copy owned by the
     wrapper (alloc = SWIG_NEWOBJ, released by the freearg typemap when the wrapper returns, exactly the
     lifetime SWIG_OLDOBJ had: no callee keeps the pointer, the two asynchronous ones - ePicLoad (Cfilepara)
     and eBackgroundFileEraser - strdup it first);
   - anything that is not a str as in SWIG (a wrapped char *, None -> NULL, otherwise TypeError), looked up with
     no Python error set. No path returns with a Python error set. */
%fragment("hds_AsCharPtr", "header", fragment="SWIG_pchar_descriptor") %{
SWIGINTERN int
hds_AsCharPtr(PyObject *obj, char **cptr, int *alloc)
{
	if (alloc)
		*alloc = SWIG_OLDOBJ;
	if (PyUnicode_Check(obj))
	{
		Py_ssize_t len = 0;
		const char *utf8 = PyUnicode_AsUTF8AndSize(obj, &len);
		if (utf8)
		{
			if (cptr)
				*cptr = (char *)utf8;
			return SWIG_OK;
		}
		PyErr_Clear();
		if (!cptr)
			return SWIG_OK; /* typecheck only: every str converts now */
		if (!alloc)
			return SWIG_RuntimeError; /* alloc must be set in order to clean up allocated memory */
		PyObject *bytes = PyUnicode_AsEncodedString(obj, "utf-8", "surrogateescape");
		if (!bytes)
		{
			PyErr_Clear();
			bytes = PyUnicode_AsEncodedString(obj, "utf-8", "replace");
		}
		if (!bytes)
		{
			PyErr_Clear();
			return SWIG_TypeError;
		}
		int res = SWIG_TypeError;
		char *data = 0;
		Py_ssize_t size = 0;
		if (PyBytes_AsStringAndSize(bytes, &data, &size) == 0)
		{
			char *copy = new char[size + 1];
			if (size)
				memcpy(copy, data, (size_t)size);
			copy[size] = 0;
			*cptr = copy;
			*alloc = SWIG_NEWOBJ;
			res = SWIG_OK;
		}
		else
			PyErr_Clear();
		Py_DECREF(bytes);
		return res;
	}
	PyErr_Clear();
	swig_type_info *pchar_descriptor = SWIG_pchar_descriptor();
	if (pchar_descriptor)
	{
		void *vptr = 0;
		if (SWIG_ConvertPtr(obj, &vptr, pchar_descriptor, 0) == SWIG_OK)
		{
			if (cptr)
				*cptr = (char *)vptr;
			return SWIG_OK;
		}
	}
	return SWIG_TypeError;
}
%}

%typemap(in,noblock=1,fragment="hds_AsCharPtr")
  char * (int res, char *buf = 0, int alloc = 0),
  const char * (int res, char *buf = 0, int alloc = 0) {
  res = hds_AsCharPtr($input, &buf, &alloc);
  if (!SWIG_IsOK(res)) {
    %argument_fail(res,"$type",$symname, $argnum);
  }
  $1 = %reinterpret_cast(buf, $1_ltype);
}
%typemap(freearg,noblock=1,match="in") char *, const char * {
  if (alloc$argnum == SWIG_NEWOBJ) delete[] buf$argnum;
}
%typemap(typecheck,noblock=1,precedence=SWIG_TYPECHECK_STRING,fragment="hds_AsCharPtr") char *, const char * {
  int res = hds_AsCharPtr($input, 0, 0);
  $1 = SWIG_CheckState(res);
}

%include <lib/python/swig.h>
%include <lib/base/object.h>
%include <lib/base/eenv.h>
%include <lib/base/eerror.h>

%immutable eSocketNotifier::activated;
%include <lib/base/ebase.h>
%include <lib/base/smartptr.h>
%include <lib/service/event.h>
%include <lib/service/iservice.h>
%include <lib/service/service.h>

// TODO: embed these...
%immutable ePicLoad::PictureData;
%immutable eButton::selected;
%immutable eInput::changed;
%immutable eComponentScan::statusChanged;
%immutable eComponentScan::newService;
%immutable pNavigation::m_event;
%immutable pNavigation::m_record_event;
%immutable eListbox::selectionChanged;
%immutable eDVBCI_UI::ciStateChanged;
%immutable eSocket_UI::socketStateChanged;
%immutable eDVBResourceManager::frontendUseMaskChanged;
%immutable eAVSwitch::vcr_sb_notifier;
%immutable ePythonMessagePump::recv_msg;
%immutable eDVBLocalTimeHandler::m_timeUpdated;
%immutable eRCMapper::rawKey;
%immutable eRCMapper::captureEnded;
%immutable eRCMapper::mouseEvent;
%immutable eHdsEgalizator::schimbare;
%include <lib/base/message.h>
%include <lib/base/etpm.h>
%include <lib/base/nconfig.h>
%include <lib/driver/rc.h>
%include <lib/driver/rcmapper.h>
%include <lib/gdi/fb.h>
%include <lib/gdi/font.h>
%include <lib/gdi/gpixmap.h>
%include <lib/gdi/gmaindc.h>
%include <lib/gdi/epoint.h>
%include <lib/gdi/erect.h>
%include <lib/gdi/esize.h>
%include <lib/gui/ewidget.h>
%include <lib/gui/elabel.h>
%include <lib/gui/einput.h>
%include <lib/gui/einputstring.h>
%include <lib/gui/einputnumber.h>
%include <lib/gui/epixmap.h>
%include <lib/gui/ecanvas.h>
%include <lib/gui/ebutton.h>
%include <lib/gui/ewindow.h>
%include <lib/gui/eslider.h>
%include <lib/gui/epositiongauge.h>
%include <lib/gui/ewidgetdesktop.h>
%include <lib/gui/elistbox.h>
%include <lib/gui/elistboxcontent.h>
%include <lib/gui/ewindowstyle.h>
%include <lib/gui/ewindowstyleskinned.h>
%include <lib/gui/ewidgetanimation.h>
%include <lib/gui/evideo.h>
%include <lib/gui/esubtitle.h>
%include <lib/gui/ehdsteletext.h>
%include <lib/service/listboxservice.h>
%include <lib/nav/pcore.h>
%include <lib/actions/action.h>
%include <lib/gdi/gfont.h>
%include <lib/gdi/emvi.h>
%include <lib/gdi/ecranpornire.h>
%include <lib/gdi/epng.h>
%include <lib/dvb/volume.h>
%include <lib/dvb/sec.h>
%include <lib/dvb/epgcache.h>
%include <lib/dvb/frontendparms.h>
%include <lib/dvb/dvbtime.h>
%include <lib/dvb/idvb.h>
%include <lib/dvb/dvb.h>
%include <lib/dvb/frontend.h>
%include <lib/dvb/pmt.h>
%include <lib/dvb/hdsspectru.h>
%include <lib/dvb/hdsteletext.h>
%include <lib/service/hdsegalizator.h>
%include <lib/components/scan.h>
%include <lib/components/file_eraser.h>
%include <lib/driver/avswitch.h>
%include <lib/driver/rfmod.h>
%include <lib/driver/misc_options.h>
%include <lib/driver/etimezone.h>
%include <lib/gdi/lcd.h>
%include <lib/mmi/mmi_ui.h>
%include <lib/dvb_ci/dvbci.h>
%include <lib/dvb_ci/dvbci_ui.h>
%include <lib/dvb/db.h>
%include <lib/python/python.h>
%include <lib/gdi/picload.h>
/**************  eptr  **************/

/**************  signals  **************/

template<class R> class PSignal0
{
public:
	PyObject *get();
};

%template(PSignal0V) PSignal0<void>;

%typemap(out) PSignal0V {
	$1 = $input->get();
}

template<class R, class P0> class PSignal1
{
public:
	PyObject *get();
};

%template(PSignal1VI) PSignal1<void,int>;
%template(PSignal1VS) PSignal1<void,const char *c>;

%typemap(out) PSignal1VI {
	$1 = $input->get();
}

%typemap(out) PSignal1VS {
	$1 = $input->get();
}

template<class R, class P0, class P1> class PSignal2
{
public:
	PyObject *get();
};

%template(PSignal2VoidIRecordableServiceInt) PSignal2<void,ePtr<iRecordableService>&,int>;

%typemap(out) PSignal2VoidIRecordableServiceInt {
	$1 = $input->get();
}

%{
RESULT SwigFromPython(ePtr<gPixmap> &result, PyObject *obj)
{	
	ePtr<gPixmap> *res;

	res = 0;
	result = 0;
#ifndef SWIGTYPE_p_ePtrT_gPixmap_t
#define SWIGTYPE_p_ePtrT_gPixmap_t SWIGTYPE_p_ePtrTgPixmap_t
#endif
	if (SWIG_Python_ConvertPtr(obj, (void **)&res, SWIGTYPE_p_ePtrT_gPixmap_t, SWIG_POINTER_EXCEPTION | 0))
		return -1;
	if (!res)
		return -1;
	result = *res;
	return 0;
}
PyObject *New_eServiceReference(const eServiceReference &ref)
{
    eServiceReference *result = new eServiceReference(ref);
    return SWIG_NewPointerObj((void*)(result), SWIGTYPE_p_eServiceReference, 1);
}
PyObject *New_iRecordableServicePtr(const ePtr<iRecordableService> &ptr)
{
    ePtr<iRecordableService> *result = new ePtr<iRecordableService>(ptr);
#ifndef SWIGTYPE_p_ePtrT_iRecordableService_t
#define SWIGTYPE_p_ePtrT_iRecordableService_t SWIGTYPE_p_ePtrTiRecordableService_t
#endif
    return SWIG_NewPointerObj((void*)(result), SWIGTYPE_p_ePtrT_iRecordableService_t, 1);
}
%}

/* needed for service groups */

PyObject *getBestPlayableServiceReference(const eServiceReference &bouquet_ref, const eServiceReference &ignore, bool simulate=false);
%{
PyObject *getBestPlayableServiceReference(const eServiceReference &bouquet_ref, const eServiceReference &ignore, bool simulate=false)
{
	eStaticServiceDVBBouquetInformation info;
	if (info.isPlayable(bouquet_ref, ignore, simulate))
		return New_eServiceReference(info.getPlayableService());
	Py_INCREF(Py_None);
	return Py_None;
}
%}

void setTunerTypePriorityOrder(int);
%{
void setTunerTypePriorityOrder(int order)
{
	eDVBFrontend::setTypePriorityOrder(order);
}
%}

/************** temp *****************/

	/* need a better place for this, i agree. */
%{
extern void runMainloop();
extern void quitMainloop(int exit_code);
extern eApplication *getApplication();
extern int getPrevAsciiCode();
extern void addFont(const char *filename, const char *alias, int scale_factor, int is_replacement);
extern const char *getEnigmaVersionString();
extern void dump_malloc_stats(void);
%}

extern void addFont(const char *filename, const char *alias, int scale_factor, int is_replacement);
extern int getPrevAsciiCode();
extern void runMainloop();
extern void quitMainloop(int exit_code);
extern eApplication *getApplication();
extern const char *getEnigmaVersionString();
extern void dump_malloc_stats(void);
