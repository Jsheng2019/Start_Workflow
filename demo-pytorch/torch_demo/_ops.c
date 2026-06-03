#include <Python.h>

static PyObject* ops_add(PyObject* self, PyObject* args) {
    long a, b;
    if (!PyArg_ParseTuple(args, "ll", &a, &b))
        return NULL;
    return PyLong_FromLong(a + b);
}

static PyObject* ops_version(PyObject* self, PyObject* args) {
    return PyUnicode_FromString("2.8.0.dev20250603");
}

static PyMethodDef OpsMethods[] = {
    {"add", ops_add, METH_VARARGS, "Add two integers."},
    {"version", ops_version, METH_NOARGS, "Return version string."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef ops_module = {
    PyModuleDef_HEAD_INIT,
    "_ops",
    "Torch demo native operations",
    -1,
    OpsMethods
};

PyMODINIT_FUNC PyInit__ops(void) {
    return PyModule_Create(&ops_module);
}
