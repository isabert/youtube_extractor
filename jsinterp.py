# -*- coding: utf-8 -*-
"""
Provide js decipher functions. Supports the logic of splice, swap, reverse sofar.
then use it to exec it to decipher a string to decrypted signature.
"""

import re

from .utils import (
    logger,
    re_search,
)


# --------------------------
# Implement youtube decrypt logics. i.e. support splice,swap,reverse.
# Ex.  bv=function(a){a=a.split("");av.qo(a,23);av.Ii(a,68);av.qo(a,63);av.Ii(a,18);
#                     av.m7(a,1);av.Ii(a,9);return a.join("")} #end with ';'`
#      var av={qo:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b%a.length]=c},
#              m7:function(a,b){a.splice(0,b)}, Ii:function(a){a.reverse()}}  #start/end with ';'
# and js used it in:
#      c&&(c=bv(decodeURIComponent(c)),a.set(b,encodeURIComponent(c)))        #start/end with ';' 
#  or not sure if used in:
#     ;if(h.s){var l=h.sp,m=bv(decodeURIComponent(h.s));f.set(l,encodeURIComponent(m))}for(var n in d)f.set(n,d[n]);
# --------------------------


def _split(sig=None):
    """Split string 'sig' into list. Ex: a=a.split("") => _split(a)"""
    return sig if not sig else list(sig)
def _swap0(a=None, b=None):
    """Swap two elements of list 'a'. Sofar always involve [0]"""
    # Ex: av.qo(a,23) ==> qo:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b%a.length]=c}
    if not a or not b: return a
    else: c = a[0] ; a[0] = a[b%len(a)] ; a[b%len(a)] = c; return a
def _reverse(a=None, b=None):
    """Reverse list 'a'. 'b' never used but is taken here as js seems giving more args then needed"""
    # Ex: av.Ii(a,18) ==> Ii:function(a){a.reverse()}
    return a if not a else a[::-1]
def _splice0rm(a=None, b=None):
    """Remove or add elements of list 'a'. Sofar always remove from [0] of 'b' elements"""
    # Ex: av.m7(a,1)  ==> m7:function(a,b){a.splice(0,b)}
    return a if not a or not b else a[b:]
def _join(arr=None):
    """Join list 'arr' back to string. Ex: return a.join("") => _join(a)"""
    return arr if not arr else "".join(arr)


def _map_objfunc(objfunc=None, funcname=None):
    """Map the given js object function code to a py function. Sofar support splice0rm,swap0,reverse"""
    if not objfunc or not funcname: return
    _mapping = [
        (r'\b%s:function\((\w+),(\w+)\){var\s+(\w+)=\1\[0\];\1\[0\]=\1(\[\2%%\1\.length\]);\1\4=\3}' % funcname,
            "_swap0"),
        (r'\b%s:function\((\w+)\){\1\.reverse\(\)}' % funcname, "_reverse"),
        (r'\b%s:function\((\w+),(\w+)\){\1\.splice\(0,\2\)}' % funcname, "_splice0rm"),
    ]
    for _pattern, _pyfunc in _mapping:
        if re.search(_pattern, objfunc): return _pyfunc
    # error on fall-through logic (unsupported yet)
    logger.error("unable to interpret: %s", objfunc)
    return None
 

def _obj_js(obj=None, jscode=None):
    """extract a js object, then map its functions into py funcions"""
    if not obj or not jscode: return None

    # extract funcs from the js transform object
    _pattern = r'\bvar\s*%s\s*=\s*{\s*(?P<func>.*?)\s*};' % obj
    mobj = re.search(_pattern, jscode, flags=re.S)   # use multi-line !!!
    if not mobj:
        logger.error("didn't find js object '%s'", obj)
        return {}
    else:
        logger.debug("found js object: %s" % mobj.group(0).replace("\n",""))
    # get list of obj's function which delimited by ','+'\n' that replaced to ', ' 
    _obj_funcs = mobj.group('func').replace("\n", " ").split(", ")

    # map each js obj func into py func, and build a dict of mapping
    _ret = {}
    for _func in _obj_funcs:
        _func = _func.strip()
        _pattern = r'(?P<method>\w+)\s*:\s*function\(\s*(?P<args>\S*?)\s*\)\s*{(?P<src>.*?)}'
        mobj = re.search(_pattern, _func)
        if not mobj:
            logger.error("unable to identify this as an object function: %s", _func)
            continue
        _key = obj+"."+mobj.group('method')         # used to identify js func calls
        _map = _map_objfunc(objfunc=_func, funcname=mobj.group('method'))
        if not _map: continue                       # skip unsupported func
        _ret[_key] = _map
    return _ret


def parse_js(patterns, key=None, jscode=None):
    """find and transfrom js decipher func into logics of py mapped func"""
    if not jscode or not key: return None

    # get decipher func name matching one of the patterns (key is the matching group idx)
    mobj = re_search(patterns, jscode, logging=True)
    if not mobj: return None                        # no decipher func found
    _dec_func = re.escape(mobj.group(key))          # escape specical char (necessary?)

    # find and extract the func
    _pattern = r'\b%s\s*=\s*function\s*\((?P<args>\S+?)\)\s*{\s*(?P<body>.*?)\s*}' % _dec_func
    mobj = re.search(_pattern, jscode)
    if not mobj: return None                        # didn't find func code
    else:
        logger.debug("found js decipher: %s" % mobj.group(0))
    args = mobj.group("args")                       # so far, args is a single var
    body = mobj.group("body").split(";")            # split js expressions delimited by ';'

    # transform decipher steps into a list of py mapped func. Supports: split,join,<#>.<func>()
    # NOTE: readable str is stored in cache. use eval() to convert str to expr when calling
    _ret = []       # store in order. each step is: "<func>(<args>)". sig is '@S@" in args
    _done_dct = {}  # dict of transformed object functions (sofar all from the same object)
    for i in range(len(body)):

        # a=a.split("") -> _split(a)
        _ptrn_split = r'(\w+)=\1\.split\(\s*""\s*\)'
        mobj = re.search(_ptrn_split, body[i])
        if mobj:
            _temp = "_split(@S@)"
            logger.debug("transform '%s' -> '%s'", mobj.group(0), _temp)
            _ret += [_temp] ; continue

        # return a.join("") -> _join(a)
        _ptrn_join = r'return\s*(\w+)\.join\(\s*""\s*\)'
        mobj = re.search(_ptrn_join, body[i])
        if mobj:
            _temp = "_join(@S@)"
            logger.debug("transform '%s' -> '%s'", mobj.group(0), _temp)
            _ret += [_temp] ; continue

        # obj function: DE.xx(a,b) -> _<*>(@S@,b) with *=_done_dct['DE.xx']
        _ptrn_objfunc = r'(\w+)\.(\w+)\s*\(\s*(\S*?)\s*\)'  # sofar 2nd arg is \d+ if any
        mobj = re.search(_ptrn_objfunc, body[i])
        if mobj:
            _js_func = mobj.group(1)+"."+mobj.group(2)
            _js_args = mobj.group(3).split(",")     # sofar 1st arg is always the sig
            _js_args[0] = "@S@"                     # and 2nd arg is always \d+ if any
            if _js_func not in _done_dct:
                # extract obj, map all its' funcs to py func, and add them into _done_dct
                _done_dct.update(_obj_js(obj=mobj.group(1), jscode=jscode))
                if _js_func not in _done_dct: continue  # error case. not mapped. skip
            _temp = "%s(%s)" % (_done_dct[_js_func], ",".join(_js_args))
            logger.debug("transform '%s' -> '%s'", mobj.group(0), _temp)
            _ret += [_temp] ; continue

        # error on fall-through logic (unsupported yet)
        logger.error("unable to interpret: %s", body[i])
    return _ret


def decrypt_sig(sig=None, decipher=None):
    """Decrpt a encrypted signature with given list of transformas"""
    if not sig or not decipher: return sig

    # readable str is stored in decipher cache, and eval() to turn it into py expr
    for expr in decipher:
        expr = expr.replace("@S@","sig")   # @S@ must be replaced with the sig variable name below
        sig = eval(expr)
    return sig


