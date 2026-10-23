/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/nconfig.h>
#include <lib/python/python.h>

ePyObject ePythonConfigQuery::m_queryFunc;

void ePythonConfigQuery::setQueryFunc(ePyObject queryFunc)
{
	if (m_queryFunc)
		Py_DECREF(m_queryFunc);
	m_queryFunc = queryFunc;
	if (m_queryFunc)
		Py_INCREF(m_queryFunc);
}

RESULT ePythonConfigQuery::getConfigValue(const char *key, std::string &value)
{
	if (key && PyCallable_Check(m_queryFunc))
	{
		ePyObject pArgs = PyTuple_New(1);
		PyTuple_SET_ITEM(pArgs, 0, PyUnicode_FromString(key));
		ePyObject pRet = PyObject_CallObject(m_queryFunc, pArgs);
		Py_DECREF(pArgs);
		if (pRet)
		{
			if (PyUnicode_Check(pRet))
			{
				/* a path with bytes that are not UTF-8 (a folder on a stick with Latin-1 names, e.g. the timeshift
				   path) comes with surrogates: PyUnicode_AsUTF8 returned NULL, value.assign(NULL) stopped enigma2
				   and the Python error stayed set. Like str -> std::string in enigma_python.i: the original bytes
				   ("surrogateescape"), otherwise '?' ("replace"), and no Python error left set. */
				int ret = 0;
				const char *utf8 = PyUnicode_AsUTF8(pRet);
				if (utf8)
					value.assign(utf8);
				else
				{
					PyErr_Clear();
					ePyObject bytes = PyUnicode_AsEncodedString(pRet, "utf-8", "surrogateescape");
					if (!bytes)
					{
						PyErr_Clear();
						bytes = PyUnicode_AsEncodedString(pRet, "utf-8", "replace");
					}
					if (bytes)
					{
						value.assign(PyBytes_AS_STRING(bytes));
						Py_DECREF(bytes);
					}
					else
					{
						PyErr_Clear();
						ret = -1;
					}
				}
				Py_DECREF(pRet);
				return ret;
			}
			Py_DECREF(pRet);
		}
	}
	return -1;
}
