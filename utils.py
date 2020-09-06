# -*- coding: utf-8 -*-
"""
Various util functions for the program
"""

import re
import logging
import random
import gzip
import urllib.request as request    # Request,urlopen,etc.
import urllib.parse as parse        # urlencode,etc for parsing url
from urllib.error import HTTPError
import json
import codecs
import math
import time
import os

# --------------------------
# Set up program's logger
# --------------------------

def set_logging(log_lvl=logging.ERROR, log_fmt=None, log_html=False):
    """Set/update logging level and format"""
    global logger, logging_console_handler, logging_html
    if isinstance(log_fmt, logging.Formatter): logging_console_handler.setFormatter(log_fmt)
    logger.setLevel(log_lvl)
    logging_html = log_html

# configure package's top lvl logger. module lvl logger can be created with, ex:
# "module_logger=logging.getLogger(__name__)", but unnecessary to define and configure
# their handlers since all logger calls to the child will pass up to the parent.
# optionally, using logging.basicConfig(level,fromat,datefmt) to just set root logger
# without creating logger if other packages are fine with it.
logger = logging.getLogger("dlvidu")
logging_console_handler = logging.StreamHandler()
logger.addHandler(logging_console_handler)
logging_html = False        # save intermediate HTML to file or not
set_logging()               # set to ERROR lvl and python default format


def get_logginglevel():
    """Get current logging level"""
    return (logger.getEffectiveLevel(), logging_html)


# --------------------------
# file processing: log,cache
# --------------------------

def log_rsp(fn=None, data=None, jsdict=False):
    """Log response or json dict to file or gzip if logging_html is on"""
    if not (fn and data and logging_html): return
    if jsdict: data=json.dumps(data, sort_keys=True, indent=2).encode('utf-8')
    # compresslevel 0~9. default:9(most&slowest); 0=no-compress. 
    with gzip.open(fn, mode="wb", compresslevel=8) as fp:
        fp.write(data)
    logger.debug("Saved response to %s", fn)


def read_log(fn=None):
    """(DEBUG ONLY) Read response from a (gzip) file assuming utf-8"""
    if not fn: return
    with open(fn, "rb") as fp:  data = fp.read()
    # check and decompress if gzip by checking gzip header, or try anyway
    # and catch "except OSError" in case "Not a gzipped file".
    # 1) py3.5+ hex() or 2) py2/py3 base64.b16encode(data[:3]).decode("ascii").lower()
    if data[:3].hex() == "1f8b08":  # GZIP_MAGIC_NUMBER="1f8b08"
        data = gzip.decompress(data)
    logger.debug("Read %s as playback data (len=%d).", fn, len(data))
    return data.decode('utf-8')


def save_dct(fn=None, dct=None):
    """Save a dct to file"""
    if not fn: return
    # ??? to implement...
    logger.info("Saved data into %s", fn)


def read_dct(fn=None):
    """Save a dct to file"""
    if not fn: return
    _dct = {}
    # ??? to implement...
    logger.info("Read %s into dictionay", fn)
    return _dct


# --------------------------
# HTTP request/response handling
# --------------------------

def random_user_agent():
    """Randomize client side (user browswer) agent"""
    _user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s Safari/537.36'
    _vers = [
        [ "68.0.3440.%s", 103,134 ], # 32 -> 32
        [ "69.0.3497.%s",  28, 60 ], # 33 -> 65
        [ "69.0.3497.%s",  64,128 ], # 65 -> 130
        [ "70.0.%s.0",  3513,3535 ], [ "70.0.%s.1",  3513,3535 ], # 23x2 -> 153,176
        [ "70.0.3538.%s",   0, 87 ], # 88 -> 264
        [ "70.0.3538.%s",  93,124 ], # 32 -> 296
        [ "71.0.%s.0",  3539,3577 ], [ "71.0.%s.1",  3539,3577 ], # 39x2 -> 335,374
        [ "71.0.3578.%s",   0,141 ], #142 -> 516
        [ "72.0.%s.0",  3579,3625 ], [ "72.0.%s.1",  3579,3625 ], # 47x2 -> 563,610
        [ "72.0.3626.%s",   0,103 ], #104 -> 714
        [ "73.0.%s.0",  3627,3682 ], [ "73.0.%s.1",  3627,3682 ], # 56x2 -> 770,826 (3644,2675?)
        [ "73.0.3683.%s",   0,121 ], #122 -> 948
        [ "74.0.%s.0",  3684,3726 ], [ "74.0.%s.1",  3684,3726 ], # 43x2 -> 991,1034(3695-7,3707-8?)
        [ "74.0.3729.%s",   0,129 ], #130 -> 1164
        [ "75.0.%s.0",  3751,3769 ], [ "75.0.%s.1",  3751,3769 ], # 19x2 -> 1183,1202 (3760?)  -24
        [ "75.0.3770.%s",   0, 15 ], # 16 -> 1218
        [ "76.0.%s.0",  3771,3780 ], [ "76.0.%s.1",  3771,3780 ], # 10x2 -> 1228,1238
        [ "80.0.3987.%s",   0,158 ], #159 -> 1397
        [ "83.0.4103.%s",   1,116 ], #116 -> 1513
    ]
    subtot = 0
    upbound = []
    for i in range(len(_vers)):
        subtot += _vers[i][2] - _vers[i][1] + 1
        upbound.append(subtot)
    x = random.randint(0,subtot-1)
    for i in range(len(_vers)):
        if (x < upbound[i]) : break
    chosen_ver = _vers[i][0] % str(_vers[i][2]+x-upbound[i]+1)
    return _user_agent % chosen_ver


# standard http headers
std_http_headers = {
    'User-Agent': random_user_agent(),
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',             # just save html traffic, can be skipped
    'Accept-Language': 'en-us,en;q=0.5',
    # can expand with optional headers below
}


def http_get(url=None, headers=std_http_headers, qs=None, fn=None, method=None):
    """Send HTTP get or method(ex.HEAD), then decode response using its encoding charset.
       Logging the response and header/info into fn if logging level allows. 
       Return tuple of (content, response obj, charset).
    """
    if qs is not None:
        # adding more querys onto url
        url += parse.urlencode(qs)

    req = request.Request(url, headers=headers, method=method)
    # urlopen always returns an obj (http.client.HTTPResonse if http/s) as a context
    # manager that supports:
    #  - geturl()   retrieved url (can determine if a redirect was followed)
    #  - info()     meta of the page such as headers (ref: http://jkorpela.fi/http.html)
    #  - getcode()|status  HTTP status code of the response
    #  - read(<#>)  reads the response body, or upto <#> bytes.
    #  - getheaders()   list of tuple (header,value)
    # add 120s timer (default is forever) that works for http/s,ftp
    try:
        rsp = request.urlopen(req, timeout=120)
    except HTTPError as e:
        #ex: urllib.error.HTTPError: HTTP Error 403: Forbidden, 404: Not Found
        return (e, "", "utf-8")

    if method == "HEAD":
        return ("", rsp, "") 
    else:
        # decompress if Content-Encoding is gzip. Or if not given, can try anyway
        # and catch "except OSError" in case "Not a gzipped file".
        # alternative: py3.5+: data[:3].hex()=='1f8b08' (GZIP_MAGIC_NUMBER="1f8b08")
        # or py2/py3: base64.b16encode(data[:3]).decode("ascii").lower() to check gzip
        data = rsp.read()
        if rsp.getheader('Content-Encoding', "") == "gzip":
            data = gzip.decompress(data)

        # get or choose best encoding of the http response
        charset = http_charset(rsp.getheader('Content-Type', default=""), data[:1024])
        data = data.decode(charset)

        # logging the response and header/info
        log_rsp(fn, (rsp.geturl()+"\nretcode:"+str(rsp.status)+"\n======\n"+
                     str(rsp.info())+"\n======\n"+data).encode('utf-8'))
        return (data, rsp, charset) # return tuple: response body, obj, charset


def http_charset(rsptype=None, rsp1024=None):
    """Get or guess best encoding of an HTTP response"""
    # either in rsp header, (optional next check <script src=... charset=),
    # or try <meta charset=".. after <head> in 1st 1k of rsp body
    m = re.match(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\s*;\s*charset=(.+)', rsptype)
    if m:
        charset = m.group(1); return charset;
    m = re.search(br'<meta[^>]+charset=[\'"]?([^\'")]+)[ /\'">]', rsp1024)
    if m:
        charset = m.group(1).decode('ascii')
    elif rsp1024.startswith(b'\xff\xfe'):
        charset = 'utf-16'
    else:
        charset = 'utf-8'   # more widely-used encoding
    return charset


def http_stream(url=None, headers=std_http_headers, qs=None, fn=None,
                tot_bytes=None, dl_bar=None, http_chunk_size=None, block_size=1*1024):
    """Send HTTP get and streaming large data into blocks. Return no-empty if not ok.
       Call back dl_bar if any to show progress status.
    """
    if not url or not fn or not tot_bytes or not block_size: return ""
    # DO NOT accept GZIP if streaming (most-like bytedata)
    headers.pop('Accept-Encoding', None)
    if qs is not None:
        # adding more querys onto url
        url += parse.urlencode(qs)

    isRange = False             # turn on iff server supports
    # if http_chunk_size given, use HEAD to test if server accepts range in HTTPResponse obj
    if http_chunk_size:
        _tmperr, _tmprsp, _ = http_get(url, headers=headers, method="HEAD")
        if not _tmprsp: return _tmperr
        _tmpflag = _tmprsp.getheader('Accept-Ranges', default=None) # Accept-Ranges: bytes
        if _tmpflag: isRange = True
        #print(_tmprsp.info())  # DEBUG ONLY

    class _StreamContext(dict):
        __getattr__ = dict.get
        __setattr__ = dict.__setitem__
        __delattr__ = dict.__delitem__
    ctx = _StreamContext()
    # download starts (DO NOT use yield generator, >30times slow)

    with open(fn+".partial", "ab") as fp:
        # check file
        if isRange: cur_bytes = fp.tell()           # resume (caller check content not changed)
        else:       fp.seek(0,0) ; cur_bytes = 0    # restart
        ctx.begin = time.time()         # start time
        while cur_bytes < tot_bytes:    # will be just one loop if not using range
            # initialize ctx
            ctx.range_lp = cur_bytes
            # create request
            req = request.Request(url, headers=headers)
            if isRange:                 # add range in request
                ctx.chunk_sz = random.randint(int(http_chunk_size * 0.95), http_chunk_size)
                ctx.range_rp = min(ctx.range_lp+ctx.chunk_sz-1, tot_bytes-1)
                ctx.chunk_sz = ctx.range_rp - ctx.range_lp + 1  # (correct size)
                req.add_header('Range', "bytes=%d-%d" % (ctx.range_lp, ctx.range_rp))
            else:
                ctx.chunk_sz = None
                ctx.range_rp = tot_bytes

            # open stream url
            try:
                rsp = request.urlopen(req, timeout=120)
            except HTTPError as e:
                #ex: urllib.error.HTTPError: HTTP Error 403: Forbidden, 404: Not Found
                fp.close()
                return e
            #print("request(%d):%d-%d, current:%d" % (ctx.chunk_sz, ctx.range_lp, ctx.range_rp, cur_bytes)) # DEBUG ONLY
            # check Content-Range and Content-Lengh in range response
            if isRange:
                _rsp_range = rsp.getheader('Content-Range', default=None)
                #print("Content-Range: ", _rsp_range)   # DEBUG ONLY
                if _rsp_range:
                    _ptrn_range = r'bytes\s*(\d+)-(\d+)?(?:/(\d+))?'
                    # check if match request
                    _mobj = re.search(_ptrn_range, _rsp_range)
                    if _mobj:
                        _lp_range = int(_mobj.group(1))
                        _rp_range = int(_mobj.group(2)) if _mobj.group(2) else None
                        _tot_size = int(_mobj.group(3)) if _mobj.group(3) else None
                        if _lp_range != ctx.range_lp:
                            logger.error("Unexpected range reply than requested (%d): '%s'",
                                        ctx.range_lp, _rsp_range)
                            fp.seek(0,0) ; cur_bytes = 0
                            isRange = False
                            continue
                        if _rp_range and _rp_range != ctx.range_rp:
                            logger.debug("Adjust range end (%d) to server reply: '%s'",
                                         ctx.range_rp, _rsp_range)
                            ctx.range_rp = _rp_range
                        if _tot_size and _tot_size != tot_bytes:
                            logger.warning("Got a different total size: '%s'", _rsp_range)
                _rsp_length = rsp.getheader('Content-Length', default=None)
                if _rsp_length and (int(_rsp_length) != ctx.chunk_sz):
                    logger.warning("Adjusted range length %d to server reply %d",
                                    ctx.chunk_sz, int(_rsp_length))
                    ctx.chunk_sz = int(_rsp_length)

            # loop started to get data
            before = time.time()                # loop start (measure RTT to find best buffer size)
            buf_sz = block_size
            while True:
                data = rsp.read(buf_sz)
                _len = len(data)
                if _len == 0:
                    if cur_bytes < ctx.range_rp:
                        logger.warning("http stream ends prematured, %d of %d bytes",
                                        cur_bytes, ctx.range_rp)
                    break
                fp.write(data)
                cur_bytes += len(data)
                # send to the download progress callback func
                if dl_bar: dl_bar(cur_bytes, tot_bytes, ctx.begin)
                # apply rate_limit. (to implement... so far rate_limit=None)
                slow_down(ctx.begin, time.time(), cur_bytes, rate_limit=None)

                # adjust buf_sz (like tcp win size. /2 or *2) (MAY NOT HELP MUCH)
                _nmin = max(_len/2.0, 1.0)
                _nmax = min(_len*2.0, 4194304)  # Do not surpass 4MB
                after = time.time()
                _elapsed = after - before
                before = after                  # set new loop start time
                if _elapsed < 0.001:            # =_len*1000 MB/s
                    buf_sz = int(_nmax)         # network very fast (RTT<1ms)
                elif _len/_elapsed > _nmax:
                    buf_sz = int(_nmax)         # > _len MB/s (i.e. RTT<1s)
                else:
                    buf_sz = int(_nmin)
                #print("buffer size: ",buf_sz)  # DEBUG ONLY

            # one chunk done
            if cur_bytes == ctx.range_lp:       # nothing downloaded in the chunk
                break
        # download done
        pass

    # rename file
    os.rename(fn+".partial", fn)
    return ""


def slow_down(start_epoch=None, now=None, received=0, rate_limit=None):
    """Slow download speed if over the rate_limit"""
    if (not rate_limit) or (received == 0) or (not start_epoch) or (not now):
        return
    _elapsed = now - start_epoch
    if _elapsed <= 0.0: return
    _speed = float(received) / _elapsed
    if _speed > rate_limit:
        _sleep_time = float(received) / rate_limit - _elapsed
        if _sleep_time > 0: time.sleep(_sleep_time)


def sanity_url(url):
    """Sanity check the format of url and return none if not"""
    if not url: return None
    return url.strip() if re.match(r'^(?:[a-zA-Z][\da-zA-Z.+-]*:)?//', url) else None


# --------------------------
# JS and JSON handling
# --------------------------
# Notes: JSON object and Python object conversion table
# * JSON  : object array string numbers   true/false null
# * Python: dict   list  str    int,float True/False None
#                  tuple

def json_load(jstr):
    """load a json string into python"""
    if not jstr: return None
    if not isinstance(jstr, str):
        logger.warning("can't load json: %s ...", jstr[:50])
        return None
    try:
        res = json.loads(jstr)
    except JSONDecodeError as e:
        logger.error("%s at (%d,%d)", e.msg, e.lineno, e.colno)
        return None
    return res


def str_decode(estr=None, part=None):   # needed??, js
    """Decode(Unescape) a string in the specified part"""
    # https://docs.python.org/3/library/codecs.html
    unicode_escape = codecs.getdecoder('unicode_escape')
    if   part == "uppercase_escape":
        return re.sub(r'\\U[0-9a-fA-F]{8}', lambda m: unicode_escape(m.group(0))[0], estr)
    elif part == "lowercase_escape":
        return re.sub(r'\\u[0-9a-fA-F]{4}', lambda m: unicode_escape(m.group(0))[0], estr)
    else: return estr


# --------------------------
# Enhanced system utils
# --------------------------

def re_search(patterns, string, ret_idx=False, flags=0, logging=True):
    """Enhance re.search to support multi patterns, with optional search flags.
       return MatchObj or tuple (MatchObj,idx) if ret_idx is set for idx the pattern
    """
    if type(patterns) == str:
        patterns = [patterns]   # convert pattern to 1-elem list
    found = False
    for idx in range(len(patterns)):
        p = patterns[idx]
        r = re.compile(r''+p, flags)
        m = r.search(string)
        if m: found = True; break;
    if not found: idx = -1
    else:
       logger.debug("pattern '%s' matched. results: %s", p, m.group(0) if logging else "...skipped...")
    if ret_idx: return (m, idx)
    else:       return m


# --------------------------
# String/Time format conversion
# --------------------------

def float_to_srt_time(flt):
    """Convert 4.22 to 00:00:04.220"""
    frac,inte = math.modf(flt)
    insec = time.strftime("%H:%M:%S", time.gmtime(inte))    # use as epoch sec
    inms  = "{:03.0f}".format(frac*1000)                    # pad/trunc to ms
    return insec+","+inms


