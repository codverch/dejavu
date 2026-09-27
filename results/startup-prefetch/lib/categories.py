"""Activity categories of executed code: (category, module regex, function regex), first match wins.

Used to say what the application is doing in an instruction or an interval: ld.so relocation,
Python type setup, .pyc unmarshal, and so on. Shared by the creation-region analysis (W1) and the
wave figures, so both use the same words.
"""
import re

# (category, module regex, function regex); evaluated in order
RULES = [
    ("ld.so: relocation", r"^ld-linux", r"^(_dl_relocate_object|elf_machine_\w+|_dl_protect_relro)$"),
    ("ld.so: symbol lookup", r"^ld-linux", r"^(do_lookup_x|_dl_lookup_symbol_x|check_match|strcmp|_dl_name_match_p|_dl_fixup|_dl_runtime_\w+|_dl_check_map_versions|match_symbol)$"),
    ("ld.so: load & map", r"^ld-linux", r"."),
    ("libc: string/memory ops", r"^libc\.so", r"^__(mem\w+|str\w+|stp\w+|wmem\w+|wcs\w+)_(avx2|evex|sse2\w*|erms\w*)|^(memcpy|memmove|memset|strlen|strchr|strcmp)$"),
    ("codec / locale", r".", r"gconv|wcsrtombs|mbstowcs|mbrtowc|mbsrtowcs|setlocale|_nl_|DecodeUTF8|Decode\w*Locale|utf_8|_Py_DecodeLocale|_Py_EncodeLocale|nl_langinfo|wcstombs|_PyUnicode_DecodeUnicodeEscape"),
    ("allocation", r".", r"^(_PyObject_Malloc|_PyObject_Free|pymalloc_\w+|PyObject_Malloc|PyObject_Free|PyMem_\w+|_PyMem_\w+|_PyObject_GC_(Alloc|New|NewVar|Malloc|Resize)|_int_malloc|_int_free|malloc|free|calloc|realloc|malloc_consolidate|_int_realloc|sysmalloc|tcache_\w+|unlink_chunk\w*|new_arena)$"),
    ("Python: GC", r"python|libpython", r"^(collect\w*|visit_\w+|subtract_refs|move_unreachable|update_refs|gc_\w+|dict_traverse|tupletraverse|list_traverse|func_traverse|type_traverse|subtype_traverse|\w+_traverse)$"),
    ("Python: type setup", r"python|libpython", r"^(PyType_Ready|type_new\w*|add_operators|add_methods|add_getset|add_members|add_subclass|inherit_\w+|type_ready\w*|_PyStaticType\w*|PyType_\w+|update_one_slot|update_slot\w*|fixup_slot_dispatchers|slotptr|resolve_slotdups|type_mro_impl|mro_\w+|_PyType_\w+|PyDescr_New\w+|descr_new)$"),
    ("Python: unmarshal .pyc", r"python|libpython", r"^(r_\w+|PyMarshal_\w+|read_object|marshal_loads\w*|_Py_Unmarshal\w*|r_object)$"),
    ("Python: dict / hash / str", r"python|libpython", r"^(lookdict\w*|pysiphash|siphash\w*|_Py_HashBytes|PyDict_\w+|_PyDict_\w+|insertdict|insert_to_emptydict|dictresize|build_indices\w*|find_empty_slot|new_keys_object|PyUnicode_InternInPlace|PyUnicode_\w+|_PyUnicode_\w+|unicode_\w+|unicodekeys_lookup\w*|intern_\w+|_PyUnicodeWriter\w*|dict_\w+)$"),
    ("Python: bytecode eval", r"python|libpython", r"^(_PyEval_EvalFrameDefault|_PyEval_\w+|call_function|_PyFunction_Vectorcall|function_code_fastcall|_PyObject_Vectorcall\w*|PyObject_Call\w*|_PyObject_Call\w*|cfunction_\w+|method_vectorcall\w*|vectorcall_\w+|slot_tp_\w+|PyObject_GetAttr|PyObject_GenericGetAttr|_PyObject_GenericGetAttrWithDict|_PyObject_LookupAttr|_PyType_Lookup|PyFrame_\w+|_PyFrame_\w+|frame_dealloc|builtin_\w+|_Py_CheckFunctionResult)$"),
    ("Python: other interpreter", r"python|libpython", r"."),
    ("shell (bash/dash)", r"^(bash|dash)$", r"."),
    ("native tool's own code", r"^(grep|find|git|sed|mawk|tail|head|tr|dirname|uname|ls|chmod)$", r"."),
    ("libc: regex", r"^libc\.so", r"^(re_\w+|__re_\w+|regexec|__regexec|regcomp|build_trtable|transit_state\w*|check_\w+_state\w*|create_\w+_state|re_string_\w+|parse_\w+|peek_token|calc_\w+|lower_subexps?|optimize_subexps|link_nfa_nodes|duplicate_node\w*|merge_state_\w+|group_nodes_into_DFAstates|build_charclass\w*|re_node_set_\w+|re_dfa_add_node|register_state|re_acquire_state\w*|sift_\w+|update_cur_sifted_state|add_epsilon_src_nodes|prune_impossible_nodes|set_regs|proceed_next_node)$"),
    ("libc: stdio", r"^libc\.so", r"^(__GI__IO_\w+|_IO_\w+|__vfprintf\w*|vfprintf\w*|buffered_vfprintf|printf_positional|fwrite|fputs\w*|__printf_fp\w*|_itoa_word|__GI___fxstat\w*|new_do_write)$"),
    ("libc: other", r"^libc\.so", r"."),
    ("other", r".", r"."),
]
CATS = [r[0] for r in RULES] + ["private/unmapped code"]
_rx = [(c, re.compile(m), re.compile(f)) for c, m, f in RULES]


def category(mod: str, fn: str) -> int:
    for i, (c, m, f) in enumerate(_rx):
        if m.search(mod) and f.search(fn):
            return i
    return len(RULES) - 1
