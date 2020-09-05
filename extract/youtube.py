# -*- coding: utf-8 -*-
"""
Youtube extractor
"""

import re, sys, os
from collections import OrderedDict as ordereddict
import urllib.parse as parse
import xml.etree.ElementTree as et
import html
import time

from .base_extractor import BaseExtractor
from ..utils import (
    logger,
    log_rsp,
    save_dct,
    read_dct,
    http_get,
    http_stream,
    slow_down,
    sanity_url,
    json_load,
    str_decode,
    re_search,
    float_to_srt_time,
)
from ..jsinterp import (
    parse_js,
    decrypt_sig,
)

# constant and variable
_PATTERN_VIDU_ID = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
_TMPLT_WATCH_URL = "https://www.youtube.com/watch?v={}"             # may skip 'www'
_TMPLT_EMBED_URL = "https://www.youtube.com/embed/{}"
_TMPLT_ERUL      = "https://youtube.googleapis.com/v/{}"
_TMPLT_VIDU_INFO_URL = "https://www.youtube.com/get_video_info?"    # may skip 'www'

# video information template
_VIDU_INFO_TMPLT = {
    "orig_url" :        "",         # user input url
    "vidu_id" :         None,       # video ID uniquely for the content
    "watch_url" :       None,       # normalized url /watch?v=<video_id>
    "watch_rsp" :       None,       # html content of watch_url
    "embed_url" :       None,       # embed page (for age restricted)
    "embed_rsp" :       None,       # html content of embed_url ("sts" etc)
    "eurl" :            None,       # Google APIs for video auth in this case
    "age_limit" :       False,      # age restricted or not
    "vidu_info" :       None,       # video info got via get_video_info link
    "js_url" :          None,       # js url for the video
    "js_rsp" :          None,       # html contect of js_url
    "js_cache" :        {},         # cached js player decipher
    "js_playerid" :     None,       # js player id for this vidu
    "title" :           None,
    "description" :     None,
    "streams" :         [],         # list of stream dict (below)
    "dashmpds" :        [],         # list of dash manifest url
    "encoded_url_map" : None,       # list of 'url_encoded_fmt_stream_map' & 'adaptive_fmts'
    "captions" :        [],         # list of captions/subtitles
    "chapters" :        [],         # list of chapters
}

# stream data template (useful set of info)
_STREAM_TMPLT = {
    "itag" :            "-1",       # -'itag'
    "url" :             "-1",       # quote url from stream info -'url' or decrypted from cipher
    "cipher" :          "-1",       # cipher dict: "url", & ... -'signatureCipher'/'cipher'
                                    # 1) "sp","s" for encrypted, 2) "sig" gives signature for unencryped
    "file_sz" :         "-1",       # size in byte -'contentLength'
    "last_modify" :     "-1",       # in epoch us - 'lastModified'
    "width" :           "-1",       # -'width' or from itag table
    "height" :          "-1",       # -'height' or from itag table
    "dura_ms" :         "-1",       # duration in ms -'approxDurationMs'
    "mimetype" :        "-1",       # ex. video/mp4; codecs=\"avc1.42001E, mp4a.40.2\" -'mimeType'
    "mime" :            "-1",       # ex. video/mp4, video/webm, audio/mp4, audio/webm -'mime' in url
    "abr" :             "-1",       # -'averageBitrate'
    "quality" :         "-1",       # (muxed video) tiny,small,medium -'quality'
    "aquality" :        "-1",       # -'audioQuality'
    "asr" :             "-1",       # (audio) ex.44100,48000 -'audioSampleRate'
    "label" :           "-1",       # ex.240p -'qualityLabel'
    "acodec" :          "-1",       # part of mimetype
    "vcodec" :          "-1",       # part of mimetype
    "type" :            "-1",       # '+'=video&audio, 'V'=video only, 'A'=audio only
    "ext" :             "-1",       # ex. mp4, webm etc. part of mime
    "order" :           "  ",       # final recommended stream(s) to download
}
# otherfields: bitrate,fps


class YoutubeER(BaseExtractor):
    """Extractor for Youtube video"""
    def __init__(self):
        self.params = dict(_VIDU_INFO_TMPLT)
        # flush the list and dict (if it uses append/update later on)
        self.params['streams'] = []
        self.params['dashmpds'] = []
        self.params['captions'] = []
        
        self.er_id = __class__.__name__[:-2] # remove ER suffix
        # load cached js info if any
        self.params['js_cache'] = read_dct(fn="%s_jscache.txt" % self.er_id)


    def _fetch_info(self, url):
        """Implement parent method to fetch url info into params"""
        self.params['orig_url'] = url

        # video id part of /watch?v=<video_id> or /<video-id>
        mobj = re_search(_PATTERN_VIDU_ID, url, ret_idx=False)
        if mobj is None:
            logger.error("%s didn't find video ID in %s.", self.__class__, url)
            return
        else:
            vidu_id = mobj.group(1)
            self.params['vidu_id'] = vidu_id
            logger.debug("video ID = %s" % vidu_id)
        # normalized url and other possible forms of url
        self.params['watch_url'] = _TMPLT_WATCH_URL.format(vidu_id)
        self.params['embed_url'] = _TMPLT_EMBED_URL.format(vidu_id)
        self.params['eurl']      = _TMPLT_ERUL.format(vidu_id)

        # additional in youtube url query:
        #   has_verified=1  will pass age-restriction
        #   bpctr="9"*10  controversial content (may be offensive or inappropriate for some viewers)
        #                 will get a bpctr after required confirmation. Works on watch page.
        #   disable_polymer=true  disalbe youtube new "Polymer" framework
        self.params['watch_url'] += "&gl=US&hl=en&has_verified=1&bpctr=9999999999"
        self.params['watch_url'] += "&disable_polymer=true"

        # get the page, and logging html with header/info etc if logging level requires
        logger.info("%s: downloading webpage", vidu_id)
        wdata, wrsp, charset = http_get(url=self.params['watch_url'],
                                        fn="%s__html.gz" % vidu_id)
        self.params['watch_rsp'] = wdata

        # check if age gated and get get_video_info via Google APIs
        mobjd = re_search(r'player-age-gate-content">', wdata)  # search in player data   (1:yt) (less working)
        mobjp = re_search(r'og:restrictions:age', wdata)        # search in meta property (2:py)
        self.params['age_limit'] = (mobjd != None or mobjp != None)

        if self.params['age_limit']:
            logger.info("%s: player-gate=%s,og-restriction=%s", vidu_id, mobjd != None, mobjp != None)

            # get embed page for "sts" etc, and logging it with header/info if logging level set
            logger.info("%s: downloading embed", vidu_id)
            edata, ersp, charset = http_get(url=self.params['embed_url'],
                                            fn="%s__embed.gz" % vidu_id)
            self.params['embed_rsp'] = edata

            # simu the access to video info via eurl (Google APIs), to view without login youtube
            mobj = re_search(r'"sts"\s*:\s*(\d+)', edata)   # SessionT*S* for sync requests ???
            sts = mobj.group(1) if mobj else ""             # found "STS" in wdata not edata ???
            qs = ordereddict( [("video_id", vidu_id),
                               ("eurl", self.params['eurl']),   # may need parse.quote() url
                                # if non-age, "sts"="" or skip, and "el"="$el"/"embeded","ps"="default","hl"="en_US"
                               ("sts", sts)]
                            ) # order really matter?
            # get video info, and logging it if logging level set
            logger.info("%s: downloading video info", vidu_id)
            vdata, vrsp, charset = http_get(url=_TMPLT_VIDU_INFO_URL, qs=qs,
                                            fn="%s__viduinfo.gz" % vidu_id)
            self.params['vidu_info'] = vdata


    def _decipher_js(self):
        """Convert js decipher func to py func, assuming js stored in params['js_rsp']"""
        _patterns = [
            r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,                # noqa: E501
            r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(' , # noqa: E501
            r'(?:\b|[^a-zA-Z0-9$])(?P<sig>[a-zA-Z0-9$]{2})\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)' , # new # noqa: E501
            r'\b(?P<sig>[a-zA-Z0-9$]{2})\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)' , # \b & {2}      # noqa: E501
            r'(?P<sig>[a-zA-Z0-9$]+)\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)' ,     # old format
            # Obsolete patterns
            r'(["\'])signature\1\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,
            r'\.sig\|\|(?P<sig>[a-zA-Z0-9$]+)\(' ,
            r'yt\.akamaized\.net/\)\s*\|\|\s*.*?\s*[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?\s*(?P<sig>[a-zA-* Z0-9$]+)\(' , # noqa: E501
            r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,                         # noqa: E501
            r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,          # noqa: E501
            r'\bc\s*&&\s*a\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,               # noqa: E501
            r'\bc\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(' ,    # noqa: E501
            ]
        _py_decipher = parse_js(_patterns, key="sig", jscode=self.params['js_rsp'])
        return _py_decipher
        # NOTE: js callstack:
        #   1) ...,q=Bw(f.url,f.sp,f.s,d);...
        #   2) Bw=function(a,b,c,d){...;c&&(c=bv(decodeURIComponent(c)),a.set(b,encodeURIComponent(c)));...};
        #   3) bv=function.....


    def _extract_info(self):
        """Implement parent method to extract video/stream info"""
        # video info are in watch html, but is in get_video_info html if restricted (1:yt)
        # or, can use two versions of get_video_info anyway for non-/restricted     (2:py)
        vidu_id = self.params['vidu_id']

        def _dashmpd_info(page=None, plrsp=None):
            """DASH MPD extraction and updated dashmpds param"""
            # in some case, video or live is segmented into seconds using DASH. Various qualities provided.
            # MPEG-DASH: https://en.wikipedia.org/wiki/Dynamic_Adaptive_Streaming_over_HTTP
            # it lists URLs of DASH MPD in "dashmpd" in html, or under player_response.
            # DASH manifest, MPD(Media Presentation Description), has this XML schema (can parse via XML):
            # https://standards.iso.org/ittf/PubliclyAvailableStandards/MPEG-DASH_schema_files/DASH-MPD.xsd

            # check in video/player response 'dashmpd'
            if page and (page != plrsp):
                _dashmpd = page.get('dashmpd', None)   # get returns none if no key instead of keyerror
                if _dashmpd and _dashmpd[0] not in self.params['dashmpds']:
                    self.params['dashmpds'].append(_dashmpd[0])
                    logger.warning("%s: dashmpd in video info unsupported yet. %s", vidu_id, _dashmpd) #???
            # check in player response 'streamingData'->'dashManifestUrl'
            if plrsp and plrsp.get('streamingDatia',{}).get('dashManifestUrl'):
                _dashmpd = plrsp['streamingData']['dashManifestUrl'].strip()
                if not _dashmpd: return
                if sanity_url(_dashmpd) and _dashmpd not in self.params['dashmpds']:
                    self.params['dashmpds'].append(_dashmpd)
                    logger.warning("%s: dashManifestUrl in player info unsupported yet. %s", vidu_id, _dashmpd) #???
                else:
                    logger.error("%s: invalid dashManifestUrl in player response. %s", vidu_id, _dashmpd)

        def _fetch_js(plcfg=None):
            """Fetch base js given in plcfg['assets']['js'] from watch or embed html, and return the js player id"""
            # extract js path and get js player id etc. Ex."js": "/s/player/c718385a/player_ias.vflset/en_US/base.js"
            _jspath = plcfg.get('assets',{}).get('js')
            self.params['js_url'] = "https://www.youtube.com"+_jspath
            _patterns = [
                r'/(?P<id>[a-zA-Z0-9_-]{8,})/player_ias\.vflset(?:/[a-zA-Z]{2,3}_[a-zA-Z]{2,3})?/base\.(?P<ext>[a-z]+)$',
                r'\b(?P<id>vfl[a-zA-Z0-9_-]+)\b.*?\.(?P<ext>[a-z]+)$',
                ]
            if not self.params['js_playerid']:  # this just done once per vidu
                mobj = re_search(_patterns, _jspath)
                if not mobj:
                    logger.error("%s: couldn't find js player id in %s", vidu_id, _jspath)
                    return None
                _js_playerid = mobj.group('ext') + "_" + mobj.group('id')
                self.params['js_playerid'] = _js_playerid
            else:
                _js_playerid = self.params['js_playerid']

            # this func is called when a url needs signature since the decipher func is in js
            # so check if decipher is in cache, and if not, fetch base js, and logging it if logging level requires
            if _js_playerid in self.params['js_cache']: return _js_playerid
            logger.info("%s: downloading player js", vidu_id)
            jdata, jrsp, charset = http_get(url=self.params['js_url'], fn="%s__js.gz" % vidu_id)
            self.params['js_rsp'] = jdata

            # then call function to extract the decipher and store in cache.
            _py_decipher = self._decipher_js()
            if _py_decipher:
                self.params['js_cache'][_js_playerid] = _py_decipher
                save_dct(fn="%s_jscache.txt" % self.er_id, dct=self.params['js_cache']) 
            return _js_playerid


        # video info is in watch html under player config, or directly in get_video_info html.
        # js is under player config in watch html or in embed if restricted.  useful elements:
        #  - /assets/js | css                           # (/assets/css is not used)
        #  - /args/player_response/.. (watch html) , or, /player_response/.. (get_video_info page)
        #        ../streamingData/formats               #muxed streams
        #                        /adaptiveFormats       #adaptive streams
        #                        /dashManifestUrl | hlsManifestUrl
        #        ../videoDetails/Title                  # video title
        #                       /shortDescription       # short info showed under video (some has chapters)
        #                       /useCipher              # true or false  (not checked yet)
        #                       /playabilityStatus/*    # reason/status etc.
        #                       /channelId | isPrivate | thumbnail/thumbnais | lengthSeconds | viewCount ...
        #        ../captions/playerCaptionsTracklistRenderer/..
        #            ../captionTracks                   # list of {baseUrl|name/simpleText|languageCode|kind|..}
        #        ../microformat                         # (additional info)
        # - /args/url_encoded_fmt_stream_map            # muxed (video+audio) streams (old format???)
        #         adaptive_fmts                         # adaptive (video or auido) streams (old format???)
        if self.params['age_limit']:
            _patterns = [ r";yt\.setConfig\(\{'PLAYER_CONFIG':\s*({.+?})(,'EXPERIMENT_FLAGS'|;)",  # noqa: E501
                          r"\byt\.setConfig\(\{.*'PLAYER_CONFIG':\s*({.+?})\}\)",
                          r";yt\.setConfig\(\{'PLAYER_CONFIG':\s*({.+?})\}\)",
                        ]
            mobj = re_search(_patterns, self.params['embed_rsp'], logging=False)
            plcfg = mobj.group(1) if mobj else None
            plcfg = json_load(plcfg)
            # player config in embed html only has useful js url. its embedded_player_response unuseful yet 
            if not plcfg:
                logger.error("%s: not found yt.setConfig", vidu_id)
                return
            log_rsp(vidu_id+"__eplcfg.gz", jsdict=True, data=plcfg)

            # response got from get_video_info is a query string, convert it to dict first
            # parse the query string into dict (or, = {k:v for k,v in parse_qsl(<data>))
            video_info =  parse.parse_qs(self.params['vidu_info'])  # values'll be a list

            # get player_response
            player_response = json_load(video_info['player_response'][0])
            log_rsp(vidu_id+"__plrsp.gz", jsdict=True, data=player_response)

        else:
            _patterns = [ r';ytplayer\.config\s*=\s*({.+?});ytplayer',
                          r';ytplayer\.config\s*=\s*({.+?});',
                        ]
            mobj = re_search(_patterns, self.params['watch_rsp'], logging=False)
            plcfg = mobj.group(1) if mobj else None
            # may need decode the \U part of it: plcfg=str_decode(plcfg, uppercase_escape)
            plcfg = json_load(plcfg)
            video_info = {}
            player_response = None
            if plcfg:
                plcfg_args = plcfg['args']          # get player config 'args'
                if plcfg_args.get('url_encoded_fmt_stream_map') or plcfg_args.get('hlsvp'):
                    # video info maybe in plcfg args if hls or stream. read in the dict str
                    # notice same video info can get from get_video_info too but in query str as above.
                    video_info = dict((k, [v]) for k, v in args.items())
                if not video_info and plcfg_args.get('ypc_vid'):
                    logger.warning("%s: paid and rental video not supported. check preview: %s",
                                   vidu_id, plcfg_args['ypc_vid'])
                    return
                if plcfg_args.get('livestream') == '1' or plcfg_args.get('live_playback') == 1:
                    # can also check plcfg['player_response']['playabilityStatus'][liveStreamability]???
                    logger.error("%s: live stream not supported yet.", vidu_id)
                    return
                # get player response 
                player_response = json_load(plcfg_args['player_response'])
            else:
                logger.error("%s: not found ytplayer.config", vidu_id)
                return
            log_rsp(vidu_id+"__plrsp.gz", jsdict=True,
                    data=dict(list(player_response.items())+[("../../assets",plcfg.get('assets'))]))

        # MUSH have video_info, player_response. plcfg is used later when requires signature !!
        if not video_info and not player_response:  return

        # get videoDetails info
        _temp = player_response.get('videoDetails',{}).get('title')
        self.params['title'] = re.sub(r'[!$/\[\]*?&|+]', "_", _temp) # other: *?&|+
        self.params['description'] = player_response.get('videoDetails',{}).get('shortDescription')

        # get dashmpd info from video_info and player_response
        _dashmpd_info(page=video_info, plrsp=player_response)
        # get muxed streams and adaptive streams in video info (old format not in player rsp ???)
        # these list can be .split(",") then urllib.parse.unquote().
        _map_mux = video_info.get('url_encoded_fmt_stream_map',[''])[0]
        _map_adp = video_info.get('adaptive_fmts', [''])[0]
        if _map_mux and _map_adp: _encoded_url_map = _map_mux + "," + _map_adp
        else:                     _encoded_url_map = _map_mux + _map_adp
        self.params['encoded_url_map'] = _encoded_url_map
        if _encoded_url_map:
            logger.warning("%s: url_encoded_fmt_stream_map or adaptive_fmts unsupported yet. %s",
                           vidu_id, _encoded_url_map) #old format??? 
        # get video streaming info player_response['streamingData]['formats'] & ['streamingData]['adaptiveFormats']
        _streaming_data = player_response.get('streamingData', None)
        if not _streaming_data:
            logger.error("%s: %s", vidu_id, player_response.get('playabilityStatus',{}).get('status'))
            return
        streaming_fmts = _streaming_data.get('formats', [])
        streaming_fmts.extend(_streaming_data.get('adaptiveFormats', []))
        #logger.debug(json.dumps(streaming_fmts, indent=4))  # DEBUG PURPOSE ONLY

        # get (itag) format list from video_info (old format???)
        _itag_spec = {}
        _fmt_list = video_info.get('fmt_list', [''])[0]
        for fmt in _fmt_list.split(','):
            _spec = fmt.split('/')
            if len(_spec) <= 1: continue
            _width_height = _spec[1].split('x')
            if len(_width_height) == 2:
                _itag_spec[_spec[0]] = {
                    'resolution': _spec[1],
                    'width': _width_height[0],
                    'height': _width_height[1],
                }
        if _fmt_list:
            logger.debug("%s: extracted fmt_list. %s", vidu_id, _fmt_list)

        # SHOULD have 'streaming_fmts[]', and extract stream info
        for fmt in streaming_fmts:
            if fmt.get('drmFamilies') or fmt.get('drm_families'):
                continue                                    # DRM content???
            # get some fields if it has
            _dct = { "itag" :    fmt.get('itag'),               # int
                     "file_sz" : fmt.get('contentLength'),      # str
                     "last_modify" : fmt.get('lastModified'),   # str (in epoch us)
                     "width" :   fmt.get('width'),              # int
                     "height" :  fmt.get('height'),             # int
                     "dura_ms" : fmt.get('approxDurationMs'),   # str
                     "mimetype": fmt.get('mimeType'),           # str
                     "abr" :     fmt.get('averageBitrate'),     # int
                     "quality" : fmt.get('quality'),            # str
                     "aquality": fmt.get('audioQuality'),       # str
                     "asr" :     fmt.get('audioSampleRate'),    # str
                     "label" :   fmt.get('qualityLabel'),       # str
                   }
            # find stream url, otherwise in signatureCipher or cipher 
            _url = fmt.get('url')
            if not _url:
                _cipher = fmt.get('cipher') or fmt.get('signatureCipher')    # old&new name
                if not _cipher: continue            # if no info found, skip...
                _cipher = parse.parse_qs(_cipher)   # cipher is a query string (&-delimt) (values'll be a list)
                _dct['cipher'] = _cipher            # save, it has: url, s,sp, or sig
                _url = sanity_url(_cipher.get('url', [''])[0])
                if not _url: continue               # if url neither in cipher, skip...

                # cipher gives: 1) unencrypted 'sig', or 2) encrypted sig 's' and query name 'sp'
                if 'sig' in _cipher:
                    _url += "&signature=" + _cipher['sig'][0]
                elif 's' in _cipher:
                    # call func that fetches js and stores decipher func in cache
                    _js_playerid = _fetch_js(plcfg) # js is given in player cfg from watch or embed
                    _sig = decrypt_sig(_cipher['s'][0], self.params['js_cache'][_js_playerid])
                    # 'sp' gives the query name to use for sig. fallback to "signature" if no 'sp'
                    _sp = _cipher['sp'][0] if 'sp' in _cipher else "signature"
                    _url += "&%s=%s" % (_sp, _sig)
            else:
                _dct['cipher'] = {}                 # regular url. no sig needed.

            # some fields may be given in url or overriden by url
            _temp = parse.unquote(_url)             # unescape %xx to char default utf-8 & '.' if unknown
            _temp = parse.urlparse(_temp).query     # parse url and get the query part
            _url_dct = parse.parse_qs(_temp)        # then parse the query string (values'll be a list)
            # unsupported stream_type 3 (FORMAT_STREAM_TYPE_OTF) ???
            _stream_type = _url_dct.get('stream_type', [''])[0]
            if _stream_type == "3": continue

            # data in url overrides previous value
            # other url info: mimeType or type, size (wxh/wXh), quality, quality_label, bitrate, fps
            if ('itag' in _url_dct) and (int(_dct['itag']) != int(_url_dct['itag'][0])):
                logger.warning("%s: itag not inconsistent (url=%s) and (stream=%s)",
                                vidu_id, _url_dct['itag'][0], _dct['itag'])
                _dct['itag'] = _url_dct['itag'][0]
            if 'mime' in _url_dct: _dct['mime'] = _url_dct['mime'][0]
            if ('clen' in _url_dct) and (_dct['file_sz'] != _url_dct['clen'][0]):
                logger.warning("%s: itag=%s, content len inconsistent (url=%s) and (stream=%s)",
                                vidu_id, str(_dct['itag']), _url_dct['clen'][0], _dct['file_sz'])
                _dct['file_sz'] = _url_dct['clen'][0]
            # final touch on url
            if 'ratebypass' not in _url_dct:
                _url += "&ratebypass=yes"
            # url completed
            _dct['url'] = _url
            # final touch on file size (have to httphead for some streams)
            if not _dct['file_sz']:                 # no stream size yet
                _tempdata, _temp, _ = http_get(url=_url, method="HEAD")
                if _temp:
                    _dct['file_sz'] = _temp.getheader('Content-Length')
                else:
                    #logger.error("%s: itag=%s, HTTP %s error to head url=%s",
                    #              vidu_id, str(_dct['itag']), _tempdata, _url)
                    pass

            # extrac vcodec & acodec from mimetype
            _mime, _codecs = _dct['mimetype'].split(";")
            _type, _, _ext = _mime.partition("/")
            _ptrn_codecs = r'(?P<key>[a-zA-Z_-]+)=(?P<quote>["\']?)(?P<val>.+?)(?P=quote)(?:;|$)'
            mobj = re.search(_ptrn_codecs, _codecs)
            if mobj and mobj.group('key') == "codecs":
                _codecs = mobj.group('val').split(",")
            else:
                _codecs = ["--", "--"]
            _mime = _mime.strip() ; _type = _type.strip() ; _codecs = [ i.strip() for i in _codecs]
            if _dct['mime'] and _mime != _dct['mime']:
                logger.warning("%s: itag=%s, mime inconsistent (url=%s) and (stream=%s)",
                                vidu_id, str(_dct['itag']), _dct['mime'][0], _mime)
            _dct['ext'] = _ext.strip()
            if   _type == "video":
                if   len(_codecs) == 2:
                    _dct['type'] = "+"
                    _dct['vcodec'], _dct['acodec'] = _codecs
                elif len(_codecs) == 1:
                    _dct['type'] = "V"
                    _dct['vcodec'] = _codecs[0] ; _dct['acodec'] = ""
                else:
                    logger.warning("%s: itag=%s, unknow codecs '%s'",
                                    vidu_id, str(_dct['itag']), _codecs) 
            elif _type == "audio":
                _dct['type'] = "A" ; _dct['acodec'] = _codecs[0] ; _dct['vcodec'] = ""
            else:
                logger.error("%s: itag=%s, unknow mime type %s", vidu_id, str(_dct['itag']), _mime)

            # update & save stream info
            _sitag = str(_dct['itag'])
            if not _sitag:
                logger.warning("%s: itag not found for a stream", vidu_id)
                #continue
            _stream_info = dict(_STREAM_TMPLT)                  # start with template
            if _sitag:
                _stream_info.update(_itag_spec.get(_sitag,{}))  # update with itag info if any
            for k,v in _dct.items():
                if v is not None: _stream_info.update({k:v})    # update with extracted info
            self.params['streams'] += [_stream_info]

            # captions
            # old info: https://video.google.com/timedtext?hl=en&type=list&v=<id>&disable_polymer=true
            if "captions" in player_response:
                self.params['captions'] = player_response['captions'].get( \
                'playerCaptionsTracklistRenderer',{}).get('captionTracks',[])

        # done processing streaming_fmts
        if len(self.params['streams']) != len(streaming_fmts):
            logger.warning("%s: only %d of %d stream formats processed",
                           vidu_id, len(self.params['streams']), len(streaming_fmts))

        # chapters (from description or from json etc)
        self.params['chapters'] = self._extract_chapters()            


    def _extract_chapters(self):
        """Extract chapter info into a list and save to file"""
        # ex of output:
        #    CHAPTER01=00:00:00.000
        #    CHAPTER01NAME=Opening
        #    CHAPTER02=00:01:30.078
        #    CHAPTER02NAME=Bla..bla..
        # 1. mixed in video description.
        #    ex. \n00:00 - Intro / Pricing\n00:18 - Signal Chain for Testing\n00:39 - What\u2019s in the Box\n00:58..
        # 2. in json of watch (or js?) url: (1:yt)
        #    r'RELATED_PLAYER_ARGS["\']\s*:\s*({.+})\s*,?\s*\n' & ['watch_next_response']
        #    ['playerOverlays']['playerOverlayRenderer']['decoratedPlayerBarRenderer']
        #    ['playerBar']['chapteredPlayerBarRenderer']['chapters']
        #    -->['chapterRenderer']-->['timeRangeStartMillis']|['title']['simpleText']
        # 3. in description?: (1:yt)
        #     r'(?:^|<br\s*/>)([^<]*<a[^>]+onclick=["\']yt\.www\.watch\.player\.seekTo[^>]+>
        #       (\d{1,2}:\d{1,2}(?::\d{1,2})?)</a>[^>]*)(?=$|<br\s*/>)'
        def _chapter_from_description():
            _chps = re.findall(r'(\d{1,2}:\d{1,2}(?::\d{1,2})?)\s*-?\s*([^\n]*\n)',
                                self.params['description'])
            return [(a, b.strip()) for a,b in _chps]

        _res = []
        for _func in [_chapter_from_description]:   # possible to try several places
            _res = _func()
            if len(_res) >= 3: break;
        _vidu_id = self.params['vidu_id']
        _fn = self.params['title'] + "__chapter.txt"
        if len(_res) > 1:
            logger.debug("%s: saving video chapters to: %s" % (_vidu_id, _fn))
            with open(_fn, "w") as _fp:
                for i, (_t,_n) in enumerate(_res):
                    _fmt = "CHAPTER{idx}={time}\nCHAPTER{idx}NAME={name}\n"
                    _fp.write(_fmt.format(idx=i+1, time=_t, name=_n))
        return _res


    def _sort_streams(self):
        """Implement parent method to weigh and sort out best stream(s)"""
        # weighed dict:
        #  1) with video: height*1, mp4/webm(30,0), filesize(order*10)  (in this case mp4 preferred)
        #  2) audio only:           mp4/webm(30,0), filesize(order*10)
        #  3) best mux (gain in overhead, so *1.0012) vs best video+audio: filesize decides
        if len(self.params['streams']) == 0: return ""
        _weigh = {}
        for i in self.params['streams']:
            _idx = i['itag'] ; _weigh[_idx] = 0
            if i['type'] != "A":  _weigh[_idx] += i['height']
            if i['ext'] == "mp4": _weigh[_idx] += 30
        _sz = [(i['file_sz'], i['itag']) for i in self.params['streams']] 
        _sz.sort(key=lambda o:int(o[0]))            # sort size from low to high
        for i in range(len(_sz)): _weigh[_sz[i][1]] += (i*10)

        # sort out best mux, video, audio if any
        _topmux = None; _topaud = None; _topvid = None;
        _lenmux = 0;    _lenaud = 0;    _lenvid = 0;
        for i in self.params['streams']:
            _idx = i['itag']
            if i['type'] == "+" and (_topmux is None or _weigh[_idx] > _weigh[_topmux]):
                _topmux = _idx ; _lenmux = int(i['file_sz'])
            if i['type'] == "V" and (_topvid is None or _weigh[_idx] > _weigh[_topvid]):
                _topvid = _idx ; _lenvid = int(i['file_sz'])
            if i['type'] == "A" and (_topaud is None or _weigh[_idx] > _weigh[_topaud]):
                _topaud = _idx ; _lenaud = int(i['file_sz'])

        # pretty format key info
        _hdr = ["", "itag","AV","filesize","ext","resolution","quality","video","audio"]
        _fmtstr = "{:<3.3}{:<5.5}{:<3.3}{:<10.10}{:<6.6}{:<12.12}{:<8.8}{:<16.16}{:<16.16}"
        _ret = _fmtstr.format(*_hdr)+"\n"
        for i in self.params['streams']:
            _idx = i['itag']
            _h = str(i['height']); _w = str(i['width'])
            if _h != "-1" or _w != "-1": _reso = _w+"x"+_h
            else: _reso = ""
            if _idx == _topmux:
                if int(_lenmux*1.0012) >= (_lenvid + _lenaud): i['order'] = "1"
                else: i['order'] = "2"
            if (_idx == _topvid) or (_idx == _topaud):
                if int(_lenmux*1.0012) >= (_lenvid + _lenaud): i['order'] = "2"
                else: i['order'] = "1"
            _fmt = [ i['order'], str(i['itag']), i['type'], i['file_sz'], i['ext'],
                     _reso, i['quality'], i['vcodec'], i['acodec']     # str(_weigh[_idx])
                   ]
            _ret += _fmtstr.format(*_fmt)+"\n"

        return _ret


    def _download_streams(self, idx=None, dl_bar=None):
        """Implement parent method to download the best or 'idx' list, and call back dl_bar if any"""
        for i in self.params['streams']:
            _itag = i['itag']
            if idx and str(_itag) not in idx: continue
            if not idx and i['order'] != "1": continue

            if not i['vcodec'] or not i['acodec']:  # dash stream (either video or audio)
                # Youtube throttles chunks >~10M for dash. Useful when server accepts range
                _http_chunk_size = 10485760         # youtube throttles chunks >~10M
            else: _http_chunk_size = None           # otherwise, don't need to chunk

            _fn_pref = self.params['title'] if self.params['title'] else self.params['vidu_id']
            if   i['type'] == "+":
                _fn = "%s.%s" % (_fn_pref, i['ext'])
            elif i['type'] == "V":
                _fn = "%s__video-%s.%s" % (_fn_pref, str(_itag), i['ext'])
            elif i['type'] == "A":
                _fn = "%s__audio-%s.%s" % (_fn_pref, str(_itag), i['ext'])
            else:
                _fn = _fn_pref + "_unknowntype"

            # download
            _tot_bytes = int(i['file_sz'])
            _vidu_id = self.params['vidu_id']
            if _tot_bytes > 0:
                if os.path.isfile(_fn):                     # check if file exists and is the same
                    _tmp_time = int(os.path.getmtime(_fn))    # in whole sec
                    _tmp_size = os.path.getsize(_fn)
                    if (_tot_bytes > 0 and _tmp_size == _tot_bytes and int(i['last_modify']) > 0
                        and _tmp_time == int(int(i['last_modify'])/1000000)):
                        logger.info("%s: file '%s' already downloaded", _vidu_id, _fn)
                        continue
                logger.info("%s: downloading (%d bytes) to file: %s", _vidu_id, _tot_bytes, _fn)
                _res = http_stream(url=i['url'], fn=_fn, tot_bytes=_tot_bytes,
                                   http_chunk_size=_http_chunk_size, dl_bar=dl_bar)
                if _res:    # error returns
                    logger.error("%s: HTTP %s. URL wrong or expired", _vidu_id, _res.code)
                elif int(i['last_modify']) > 0 :
                    # set file (access time, last modified time)
                    os.utime(_fn, (time.time(), int(i['last_modify'])/1000000))


    def _list_captions(self):
        """Implement parent method to list available captions"""
        if len(self.params['captions']) <= 0: return ""
        _ret = []
        for i in self.params['captions']:
            _ret.append("{}({})".format(i['languageCode'], i.get('kind',"sub")))
        return "; ".join(_ret)


    def _vtt_to_srt(self, data):
        """Convert vtt format caption/subtitle to srt format"""
        # ex: <transcript><text start="4.22" dur="4.93">we&amp;#39re ...</test> ==>
        #     1\n00:00:04,220 --> 00:00:09.150\nwe're ...\n
        root = et.fromstring(data)
        _tmp = []
        _end = 0.0
        # vtt time overlaps in neighboring, so put start of next as end of last
        for i, obj in enumerate(root):
            _start = float(obj.attrib['start'])
            if _start < _end: _tmp[i-1][2] = _start
            _dur   = float(obj.attrib['dur'])
            _txt   = obj.text or ""                 # "  "->" ", "\n"->" " needed???
            _txt   = html.unescape(_txt)            # unescape HTML entities
            _end   = _start + _dur
            _seq   = i + 1      # enum is 0-base -> srt is 1-base
            _tmp.append([_seq, _start, _end, _txt])
        _ret = []
        for _seq, _start, _end, _txt in _tmp:
            _ret.append("{seq}\n{start} --> {end}\n{txt}\n".format(
                        seq=_seq, txt=_txt,
                        start=float_to_srt_time(_start),
                        end=float_to_srt_time(_end))
                       )
        return "\n".join(_ret).strip()


    def _download_captions(self):
        """Implement parent method to download captions"""
        _vidu_id = self.params['vidu_id']
        logger.info("%s: downloading %d captions", _vidu_id, len(self.params['captions']))
        _fn_pref = self.params['title'] if self.params['title'] else _vidu_id
        for i in self.params['captions']:
            _lang_code = i['languageCode']
            _kind = i.get('kind',"sub")             # kind is optional field
            data, rsp, _ = http_get(i['baseUrl'],
                                    fn="%s__%s-%s.gz" % (_vidu_id, _lang_code, _kind))
            _fn = "%s.%s-%s.srt" % (_fn_pref, _lang_code, _kind)
            with open(_fn, "w") as _fp:
                _fp.write(self._vtt_to_srt(data))


