/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/eerror.h>
                /* avoid warnigs :) */
#undef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200112L
extern "C" PyObject *PyInit__enigma(void);
extern "C" void eBaseInit(void);
extern "C" void eConsoleInit(void);
extern void bsodFatal(const char *component);
extern std::string bsodLogBuffer();

#define SKIP_PART2
#include <lib/python/python.h>
#undef SKIP_PART2

#ifdef PYTHON_REFCOUNT_DEBUG
ePyObject &ePyObject::operator=(PyObject *ob)
{
	m_ob=ob;
	m_file=0;
	m_line=0;
	m_from=m_to=0;
	m_erased=false;
	return *this;
}

ePyObject &ePyObject::operator=(const ePyObject &ob)
{
	m_ob=ob.m_ob;
	m_file=ob.m_file;
	m_line=ob.m_line;
	m_from=ob.m_from;
	m_to=ob.m_to;
	m_erased=ob.m_erased;
	return *this;
}

ePyObject::operator PyObject*()
{
	if (m_ob)
	{
		if (!m_erased && m_ob->ob_refcnt > 0)
			return m_ob;
		eDebug("invalid access PyObject %s with refcount <= 0 %d",
			m_erased ? "deleted" : "undeleted", m_ob->ob_refcnt);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	return 0;
}

void ePyObject::incref(const char *file, int line)
{
	if (!m_ob)
	{
		eDebug("invalid incref python object with null pointer %s %d!!!", file, line);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	if (m_erased || m_ob->ob_refcnt <= 0)
	{
		eDebug("invalid incref %s python object with refcounting value %d in file %s line %d!!!",
			m_erased ? "deleted" : "undeleted", m_ob->ob_refcnt, file, line);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	if (m_ob->ob_refcnt == 0x7FFFFFFF)
	{
		eDebug("invalid incref %s python object with refcounting value %d (MAX_INT!!!) in file %s line %d!!!",
			m_erased ? "deleted" : "undeleted", m_ob->ob_refcnt, file, line);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	m_file = file;
	m_line = line;
	m_from = m_ob->ob_refcnt;
	m_to = m_from+1;
	Py_INCREF(m_ob);
}

void ePyObject::decref(const char *file, int line)
{
	if (!m_ob)
	{
		eDebug("invalid decref python object with null pointer %s %d!!!", file, line);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	if (m_erased || m_ob->ob_refcnt <= 0)
	{
		eDebug("invalid decref %s python object with refcounting value %d in file %s line %d!!!",
			m_erased ? "deleted" : "undeleted", m_ob->ob_refcnt, file, line);
		if (m_file)
			eDebug("last modified in file %s line %d from %d to %d",
				m_file, m_line, m_from, m_to);
		bsodFatal("enigma2, refcnt");
	}
	m_file = file;
	m_line = line;
	m_from = m_ob->ob_refcnt;
	m_to = m_from-1;
	m_erased = !m_to;
	Py_DECREF(m_ob);
}
#endif  // PYTHON_REFCOUNT_DEBUG

#define SKIP_PART1
#include <lib/python/python.h>
#undef SKIP_PART1

ePython::ePython()
{
//	Py_VerboseFlag = 1;
	
//	Py_OptimizeFlag = 1;
	
	/*
	 * Py_Initialize() alone starts from the compat configuration: it ignores PYTHONUTF8 and takes the text
	 * encoding from the C locale. init starts enigma2 without LANG or LC_ALL, so that locale is "C" and
	 * open() in text mode, print() and the file name functions all use ASCII; the first non-ASCII byte
	 * (setup.xml, a service name, a file name on a stick) raises UnicodeDecodeError or UnicodeEncodeError.
	 * UTF-8 mode (PEP 540) makes Python use UTF-8 for text files, stdio and file names whatever the locale
	 * is. The public API has no compat preconfig, so the Python preconfig is used and the two fields where
	 * it differs from what Py_Initialize() would choose are set back: no C locale coercion (the C locale of
	 * the process stays as it was, so the C++ side sees the same locale as before) and no argument parsing.
	 * utf8_mode is the only real change; the environment (PYTHONMALLOC, PYTHONDEVMODE) is read as before.
	 * It has to run before anything else touches the runtime: PyImport_AppendInittab() already allocates
	 * with the raw allocator chosen by the preinitialization.
	 * If it fails, Py_Initialize() preinitializes again with the defaults and enigma2 still starts.
	 */
	PyPreConfig preconfig;
	PyPreConfig_InitPythonConfig(&preconfig);
	preconfig.utf8_mode = 1;
	preconfig.coerce_c_locale = 0;
	preconfig.coerce_c_locale_warn = 0;
	preconfig.parse_argv = 0;
	PyStatus status = Py_PreInitialize(&preconfig);
	if (PyStatus_Exception(status))
		eWarning("[ePython] UTF-8 mode not set (%s), Python keeps the locale encoding",
			status.err_msg ? status.err_msg : "unknown error");

	PyImport_AppendInittab("_enigma", PyInit__enigma);
	Py_Initialize();

	eBaseInit();
	eConsoleInit();
}

ePython::~ePython()
{
	Py_Finalize();
}

int ePython::execFile(const char *file)
{
	FILE *fp = fopen(file, "r");
	if (!fp)
		return -ENOENT;
	int ret = PyRun_SimpleFile(fp, file);
	fclose(fp);
	return ret;
}

int ePython::execute(const std::string &pythonfile, const std::string &funcname)
{
	ePyObject pFunc = resolve(pythonfile, funcname);
	if (!pFunc)
		return 1;
	if (!PyCallable_Check(pFunc))
	{
		Py_DECREF(pFunc);
		return 1;
	}
	ePyObject pArgs = PyTuple_New(0);
	ePyObject pValue;
	if (pArgs)
		pValue = PyObject_CallObject(pFunc, pArgs);
	Py_XDECREF(pArgs);
	Py_DECREF(pFunc);
	if (!pValue)
	{
		PyErr_Print();
		return 1;
	}
	long value = PyLong_AsLong(pValue);
	if (PyErr_Occurred())
	{
		PyErr_Print();
		Py_DECREF(pValue);
		return 1;
	}
	printf("Result of call: %ld\n", value);
	Py_DECREF(pValue);
	return 0;
}

/* Nici diagnosticul unei erori nu trebuie sa lase alta exceptie. */
static std::string hdsPythonText(ePyObject object)
{
	ePyObject str;
	if (object)
		str = PyObject_Str(object);
	else
		str = PyUnicode_FromString("()");
	const char *text = str ? PyUnicode_AsUTF8(str) : NULL;
	std::string result = text ? text : "?";
	if (PyErr_Occurred())
		PyErr_Print();
	if (str)
		Py_DECREF(str);
	return result;
}

/*
 * HDSatelit: an exception that comes out of a Python function called from C++ (a timer, a key, the output of a console
 * program) restarted the user interface (bsodFatal), also when it came from a plugin the user installed.
 * Components.HdsPluginExtern.trateaza(type, value, traceback, call, log) looks at the traceback: the name of the
 * external plugin when a frame is in one (the crash log, the report and the short message are its work), otherwise
 * None. call is the "(PyObject_CallObject(...) failed)" line written below, log the end of the log before the error
 * (for the report). The exception is put back as it was, for PyErr_Print. A missing module or an error in it leaves
 * everything as before.
 */
static std::string hdsPluginExtern(ePyObject pFunc, ePyObject pArgs)
{
	std::string name;
#if PY_VERSION_HEX >= 0x030C0000
	PyObject *value = PyErr_GetRaisedException();
	if (!value)
		return name;
	PyObject *type = (PyObject *)Py_TYPE(value);
	PyObject *tb = PyException_GetTraceback(value);
#else
	PyObject *type = NULL, *value = NULL, *tb = NULL;
	PyErr_Fetch(&type, &value, &tb);
	if (!type)
		return name;
	PyErr_NormalizeException(&type, &value, &tb);
	if (tb && value)
		PyException_SetTraceback(value, tb);
#endif
	std::string funcText = hdsPythonText(pFunc);
	std::string argText = hdsPythonText(pArgs);
	std::string call = "(PyObject_CallObject(" + funcText + "," + argText + ") failed)";
	std::string log = bsodLogBuffer();
	PyObject *callObj = PyUnicode_DecodeUTF8(call.c_str(), (Py_ssize_t)call.size(), "replace");
	PyObject *logObj = PyUnicode_DecodeUTF8(log.c_str(), (Py_ssize_t)log.size(), "replace");
	PyObject *module = (callObj && logObj) ? PyImport_ImportModule("Components.HdsPluginExtern") : NULL;
	PyObject *result = module ? PyObject_CallMethod(module, "trateaza", "OOOOO", type, value ? value : Py_None,
		tb ? tb : Py_None, callObj, logObj) : NULL;
	if (result && PyUnicode_Check(result))
	{
		const char *text = PyUnicode_AsUTF8(result);
		if (text)
			name = text;
	}
	if (PyErr_Occurred())
	{
		eDebug("[ePython] Components.HdsPluginExtern did not decide, the error is handled as before:");
		PyErr_Print();
		name.clear();
	}
	if (result)
		Org_Py_DECREF(result);
	if (module)
		Org_Py_DECREF(module);
	if (logObj)
		Org_Py_DECREF(logObj);
	if (callObj)
		Org_Py_DECREF(callObj);
#if PY_VERSION_HEX >= 0x030C0000
	if (tb)
		Org_Py_DECREF(tb);
	PyErr_SetRaisedException(value);
#else
	PyErr_Restore(type, value, tb);
#endif
	return name;
}

int ePython::call(ePyObject pFunc, ePyObject pArgs)
{
	int res = -1;
	ePyObject pValue;
	if (pFunc && PyCallable_Check(pFunc))
	{
		pValue = PyObject_CallObject(pFunc, pArgs);
 		if (pValue)
		{
			if (PyLong_Check(pValue))
			{
				res = PyLong_AsLong(pValue);
				if (PyErr_Occurred())
					PyErr_Print();
			}
			else
				res = 0;
			Py_DECREF(pValue);
		} else
		{
			std::string plugin = hdsPluginExtern(pFunc, pArgs);
		 	PyErr_Print();
			std::string funcText = hdsPythonText(pFunc);
			std::string argText = hdsPythonText(pArgs);
			eDebug("(PyObject_CallObject(%s,%s) failed)",
				funcText.c_str(), argText.c_str());
			/* HDSatelit: an error in an external plugin: the traceback is in the log, the user interface goes on */
			if (!plugin.empty())
			{
				eDebug("[ePython] error in the external plugin %s: no restart of the user interface", plugin.c_str());
				/* nothing may stay set for the next call into Python */
				if (PyErr_Occurred())
					PyErr_Clear();
				return res;
			}
		 	bsodFatal(0);
		}
	}
	return res;
}

ePyObject ePython::resolve(const std::string &pythonfile, const std::string &funcname)
{
	ePyObject pModule = PyImport_ImportModule(pythonfile.c_str()), pFunc;
	if (pModule)
	{
		pFunc = PyObject_GetAttrString(pModule, funcname.c_str());
		Py_DECREF(pModule);
	}
	if (PyErr_Occurred())
		PyErr_Print();
	return pFunc;
}
