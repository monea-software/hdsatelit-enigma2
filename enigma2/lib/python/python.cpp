/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/eerror.h>
                /* avoid warnigs :) */
#undef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200112L
extern "C" PyObject *PyInit__enigma(void);
extern "C" void eBaseInit(void);
extern "C" void eConsoleInit(void);
extern void bsodFatal(const char *component);

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
	ePyObject pName, pModule, pDict, pFunc, pArgs, pValue;
	pName = PyUnicode_FromString(pythonfile.c_str());

	pModule = PyImport_Import(pName);
	Py_DECREF(pName);
	
	if (pModule)
	{
		pDict = PyModule_GetDict(pModule);
		
		pFunc = PyDict_GetItemString(pDict, funcname.c_str());
		
		if (pFunc && PyCallable_Check(pFunc))
		{
			pArgs = PyTuple_New(0);
				// implement arguments..
			pValue = PyObject_CallObject(pFunc, pArgs);
			Py_DECREF(pArgs);
			if (pValue)
			{
				printf("Result of call: %ld\n", PyLong_AsLong(pValue));
				Py_DECREF(pValue);
			} else
			{
				Py_DECREF(pModule);
				PyErr_Print();
				return 1;
			}
		}
	} else
	{
		if (PyErr_Occurred())
			PyErr_Print();
		return 1;
	}
	return 0;
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
				res = PyLong_AsLong(pValue);
			else
				res = 0;
			Py_DECREF(pValue);
		} else
		{
		 	PyErr_Print();
			ePyObject FuncStr = PyObject_Str(pFunc);
			ePyObject ArgStr = PyObject_Str(pArgs);
		 	eDebug("(PyObject_CallObject(%s,%s) failed)", PyUnicode_AsUTF8(FuncStr), PyUnicode_AsUTF8(ArgStr));
			Py_DECREF(FuncStr);
			Py_DECREF(ArgStr);
		 	bsodFatal(0);
		}
	}
	return res;
}

ePyObject ePython::resolve(const std::string &pythonfile, const std::string &funcname)
{
	ePyObject pName, pModule, pDict, pFunc;

	pName = PyUnicode_FromString(pythonfile.c_str());

	pModule = PyImport_Import(pName);
	Py_DECREF(pName);
	
	if (pModule)
	{
		pDict = PyModule_GetDict(pModule);
		pFunc = PyDict_GetItemString(pDict, funcname.c_str());
		Py_XINCREF(pFunc);
		Py_DECREF(pModule);
	} else if (PyErr_Occurred())
		PyErr_Print();
	return pFunc;
}
