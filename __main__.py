#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
"""
A python script/package for saving videos from supported(*) sites
"""

import re, sys

# add script path into pythonpath for pkg search (before main())
if __package__ is None and not hasattr(sys, 'frozen'):
    # direct call of __main__.py
    import os.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))

# name of main module is always "__main__", so it always uses absolute import.
# also, "from dlvidu import *" via __init__ does't incl everything. "import dlvidu" works.
# absolute import in main module
from dlvidu.utils import (
    logger,
)
from dlvidu.extract import (    # via extract/__init__.py
    YoutubeER,
)


class DLvidu(object):
    """Core API for this program"""

    def __init__(self, req_url=None):
        """Initialize and set the program"""
        self.orig_url = req_url

        # find best-match extractor and video info
        # to be implemented...
        best_extract = YoutubeER
        self.ex_obj = best_extract()                # instance obj for each video

        self.ex_obj.fetch_info(self.orig_url)       # fetch url info

        #DEBUG: if bypass fetch_info and just playback
        #from dlvidu.utils import (read_log)
        #data = read_log("...")
        #self.ex_obj.params['...'watch_rsp'] = data # watch/embed_rsp|vidu_info|js_rsp
        #self.ex_obj.params['vidu_id'] = "..."
        #self.ex_obj.params['age_limit'] = True|False
        #self.ex_obj.params['js_cache'] = {"js_c718385a": ['_split(@S@)', '_swap0(@S@,23)', '_reverse(@S@,68)', '_swap0(@S@,63)', '_reverse(@S@,18)', '_splice0rm(@S@,1)', '_reverse(@S@,9)', '_join(@S@)']} 

        self.ex_obj.extract_info()                  # extract video/stream info


    def _get_streams(self):
        """Return stream info in lines"""
        _ret = self.ex_obj.sort_streams()           # weigh and sort out top stream(s)
        return _ret


    def _download(self, idx=None, dl_bar=None):
        """Download the best or 'idx' list if any. Call back dl_bar if any during progress"""
        self.dl_bar = dl_bar
        self.ex_obj.download_streams(idx=idx, dl_bar=dl_bar)


    def _list_captions(self):
        """Return available captions/subtitles"""
        _ret = self.ex_obj.list_captions()          # weigh and sort out top stream(s)
        return _ret


    def _captions(self):
        """Download captions/subtitles"""
        self.ex_obj.download_captions()


if __name__ == '__main__':
    py_ver = sys.version_info[0:3]  # (maj,mino,micro) of python
    if py_ver < (3,3,0):
        print("{} not supported. Need python3+".format(sys.version.split(' ')[0]))
        sys.exit(1)
    import cli
    cli.cli_main()

