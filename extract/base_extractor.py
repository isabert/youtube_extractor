# -*- coding: utf-8 -*-
"""
Base class for extractor
"""

class BaseExtractor(object):
    """Only defines the methods that an extractor shall implement"""

    def fetch_info(self, url):
        """Fetch url info"""
        return self._fetch_info(url)


    def extract_info(self):
        """Extract video/stream info"""
        return self._extract_info()


    def sort_streams(self):
        """Sort out best stream(s)"""
        return self._sort_streams()


    def download_streams(self, idx=None, dl_bar=None):
        """Download the best or 'idx' list if any. Call back dl_bar if any during progress"""
        return self._download_streams(idx=idx, dl_bar=dl_bar)


    def list_captions(self):
        """List available captions"""
        return self._list_captions()


    def download_captions(self):
        """Download capations"""
        return self._download_captions()


    #def _fetch_info(self, url):
    #    """Subclass implements to fetch url info"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass
    #def _extract_info(self):
    #    """Subclass implements to extract video/stream info"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass
    #def _sort_streams(self):
    #    """Subclass implements to sort out best stream(s)"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass
    #def _download_streams(self, idx=None, dl_bar=None):
    #    """Subclass implements to download stream(s)"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass
    #def _list_captions(self):
    #    """Subclass implements to list captions"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass
    #def _download_captions(self):
    #    """Subclass implements to download captions"""
    #    print("ERROR: shouldn't be here!!!")
    #    pass


    def _real_initialize(self):
        """Subclass implements initialization interface"""
        pass


