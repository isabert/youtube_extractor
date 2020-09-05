
"""
The CLI (Command Line Interface) entry to the python program
"""

from __future__ import unicode_literals
import sys
import shutil
import logging
import argparse
import time
import signal

# add script path into pythonpath for pkg search (before main())

if __package__ is None and not hasattr(sys, 'frozen'):
    # direct call of __main__.py
    import os.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))

# name of main module is always "__main__", so it always uses absolute import.
from ytb_ext import *    # absolute import in main module


w_size = {'w_col': 80, 'w_row': 24} # CLI terminal size


def progress_bar(curr_size, tot_size, start_epoch=None, ch="█", scale=0.68):
    """Show progress bar of downloading. Example:
    PSY - GANGNAM STYLE(강남스타일) MV.mp4
    ↳ |███████████████████████████████████████| 100.0%
    """
    w_width = int(w_size['w_col'] * scale)
    filled = int(round(w_width * curr_size / float(tot_size)))
    remaining = w_width - filled
    bar = ch * filled + " " * remaining
    percent = round(100.0 * curr_size / float(tot_size), 1)
    if start_epoch and percent >= 0.1 and (curr_size < int(tot_size)):
        secleft=int((time.time()-start_epoch) * (100-percent)/percent)
        if   secleft > 3600000:
            timeleft = "slow..."
        elif secleft > 3600:
            timeleft = "%dh %dm left  " % (int(secleft/3600), int((secleft%3600)/60))
        elif secleft > 600:
            timeleft = "%dm %ds left  " % (int(secleft/60), int(secleft%60))
        else:
            timeleft = "%ds left      " % int(secleft)
    elif curr_size == int(tot_size):
        timeleft ="done in " + time.strftime("%H:%M:%S",
                  time.gmtime(int(time.time()-start_epoch)))
    else: timeleft = ""         # when %=0
    text = " ↳ |{bar}| {percent}% ({cur:>0.1f}/{tot:<0.1f}MB){sep}{timeleft}\r".format(
            bar=bar, percent=percent, cur=curr_size/1048576, tot=tot_size/1048576,
            sep=", " if timeleft else "", timeleft=timeleft)
    # use write() to avoid newline and flush() to force buffer onto stdout 
    sys.stdout.write(text)
    if (curr_size == tot_size): sys.stdout.write("\n")
    sys.stdout.flush()


def cli_main():
    """CLI application to download video."""
    # get terminal size. default return COLUMNSxLINES=80x24 (py3.3+)
    # or use os.popen("stty size", "r").read().split()
    w_size['w_col'], w_size['w_row'] = shutil.get_terminal_size()
    parser = argparse.ArgumentParser()#description=__doc__)
    parser.add_argument("--version", action="version", version="%(prog)s "+prog_version)
    parser.add_argument("-v", action="count", dest="verbose_lvl", default=0,
        help="Upto four levels (-vvvv): warning, info, debug, details. If not given, default error level")
    parser.add_argument("-l", action="store_true", dest="list_only", default=False, help="Just list video info")
    parser.add_argument("req_url", metavar="URL(s)", nargs="?", help="Video URL")

    args = parser.parse_args()
    #TEST: ax68rWI4Tuk (funktytown) tyDvp3wjqpw (ww2 18+) tUCVN2GLYuA (asus)
    #      Wv1bl88fRf8 (3 subs) EwHIH3jIwuM (chapters) pvkTC2xIbeY (chapters,&sub+asr)
    #      7takIh1nK0s (not playable, 6hAHZRbijt8 PwrySjp4J9Q)  E0nTlSMGYyI (4k)
    #EX: args = parser.parse_args(["-vvvv", "https://www.youtube.com/watch?v=..."])

    if not args.req_url:     # video url not set or empty
        parser.print_help(); sys.exit(1);

    if args.verbose_lvl < 4:    _log_html = False;
    else: args.verbose_lvl = 4; _log_html = True;
    _llvl = ["ERROR", "WARNING", "INFO", "DEBUG", "DEBUG"]
    _nlvl = getattr(logging, _llvl[args.verbose_lvl], logging.ERROR)
    _logging_fmt = logging.Formatter(
        fmt="%(asctime)s,%(msecs)03d [%(module)s #%(lineno)d] %(levelname)s - %(message)s",
        datefmt="%H:%M:%S")     # asctime without datefmt gives Y-M-D H:M:S.s 
    set_logging(_nlvl, _logging_fmt, _log_html)

    def interrupt(signum, frame):   # given with 2 args. used for timeout userinput below
        print()
        raise ValueError("userinput timedout")  # an except with any msg
    _urls = args.req_url.split()
    for _url in _urls:
        dlv = DLvidu(_url)
        _streams = dlv._get_streams()
        if _streams == "": continue
        print(_streams)
        if args.list_only: continue
        '''
        # auto or user select
        TIMEOUT = 18  # sec
        print("Wait %s seconds to auto-download, or select ids (separate by ,), or 0 to skip: " % TIMEOUT,
              end="")
        sys.stdout.flush()
        signal.signal(signal.SIGALRM, interrupt)
        signal.alarm(TIMEOUT)
        try:
            _sel = input()
            signal.alarm(0) # disable the alarm after success
        except ValueError:
            _sel = ""
        _sel = _sel.strip().split(",")
        _sel = [i.strip() for i in _sel if i]   # will be [] if all empty
        '''

        _sel=False

        # download
        if _sel:
            dlv._download(idx=_sel, dl_bar=progress_bar)
        else:
            dlv._download(dl_bar=progress_bar)

        # capation
        _captions = dlv._list_captions()
        if _captions == "": continue
        print("Available captions/subtitles: ", _captions)
        dlv._captions()
        
    #TODO: *)save/load cache *)playlist *)rate-limit


if __name__ == '__main__':
    py_ver = sys.version_info[0:3]  # (maj,mino,micro) of python
    if py_ver < (3,3,0):
        print("{} not supported. Need python3+".format(sys.version.split(' ')[0])); exit(1)
    cli_main()

