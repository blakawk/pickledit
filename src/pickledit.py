import sys
import pickle
import pprint
import tempfile
import imp
import subprocess
import shutil
import win32event
import win32con
import win32file
import gzip
import bz2
import zipfile
import logging
from hashlib import sha256
from logging import info, debug, warn, exception
from _winreg import HKEY_LOCAL_MACHINE as HKLM, OpenKey, QueryValueEx, CloseKey
import os
from os.path import join, abspath, exists, basename, dirname

if hasattr(sys, 'frozen'):
    logfile = ".".join(abspath(sys.argv[0]).split(".")[:-1] + ["log"])
else:
    logfile = ".".join(abspath(__file__).split(".")[:-1] + ["log"])

logging.basicConfig(
    filename=logfile,
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)d %(funcName)s %(levelname)s: %(message)s",
    datefmt="%b %d %H:%M:%S",
)

def key(root, *name):
    handle = OpenKey(root, "\\".join(name[:-1]))
    (value, type) = QueryValueEx(handle, name[-1])
    CloseKey(handle)
    debug("queried registry key %r: value=%r type=%r", "\\".join([str(root)] + list(name)), value, type)
    return value

NPP = key(HKLM, "SOFTWARE", "Microsoft", "Windows", "CurrentVersion", "App Paths", "notepad++.exe", "")

magic_dict = {
    "\x1f\x8b\x08": gzip.GzipFile,
    "\x42\x5a\x68": bz2.BZ2File,
}

max_len = max(len(x) for x in magic_dict)

writer = {}

def getpickle(path):
    info("getting pickle data from %r", path)
    with open(path, 'r') as fd:
        content = fd.read()
    info("got %d bytes", len(content))
    debug("%r", content)
    for magic, fileclass in magic_dict.items():
        if content.startswith(magic):
            info("pickle compressed with %r", fileclass)
            writer[path] = fileclass
            with fileclass(path, 'r') as fd:
                content = fd.read()
            info("uncompressed %d bytes", len(content))
            debug("%r", content)
            return content
    info("pickle is not compressed")
    writer[path] = open
    return content

def pickle2text(src, dst):
    content = getpickle(src)
    if content:
        data = pickle.loads(content)
        info("loaded data")
        debug("%r", data)
        pretty = pprint.pformat(data)
        content = "data = " + pretty[0] + " \\\n " + pretty[1:-1] + "\n" + pretty[-1] + "\n"
        changed = True
        if exists(dst):
            with open(dst, 'r') as fd:
                current = fd.read()
            changed = current != content
            if changed:
                info("data has changed, updating edit file %r", dst)
        else:
            info("creating edit file %r", dst)
        if changed:
            debug("%r", content)
            with open(dst, 'w') as data_fd:
                data_fd.write(content)

def text2pickle(src, dst):
    info("dumping pickle data from %r", src)
    data = None
    with open(src, 'r') as fd:
        data_content = fd.read()
        info("got %d bytes", len(data_content))
        debug("%r", data_content)
        if data_content:
            try:
                exec(data_content)
                if data is not None:
                    info("updating pickle %r with writer %r", dst, writer[dst])
                    debug("%r", data)
                    with writer[dst](dst, 'w') as fd:
                        pickle.dump(data, fd)
                else:
                    warn("no data found in %r", src)
            except:
                exception("cannot decode data from %r", src)
        else:
            info("no data detected")

def update((src, src_handle, old_ts, old_hash), (dst, dst_handle, dst_hash), function):
    info("updating %r from %r", dst, src)
    debug("old source timestamp %r", old_ts)
    src_ts = os.stat(src).st_mtime
    debug("new source timestamp %r", src_ts)
    dst_ts = os.stat(dst).st_mtime if exists(dst) else None
    debug("destination %r timestamp is %r", dst, dst_ts)
    if dst_hash is None and exists(dst):
        digest = sha256()
        with open(dst, 'r') as fd:
            digest.update(fd.read())
        dst_hash = digest.hexdigest()
    debug("destination hash is %r", dst_hash)
    if old_ts == src_ts:
        debug("no update detected")
        return src_ts, old_hash, dst_handle, dst_ts, dst_hash
    else:
        debug("update detected in %r", src)
        digest = sha256()
        with open(src, 'r') as fd:
            digest.update(fd.read())
        if digest.hexdigest() != old_hash:
            new_hash = digest.hexdigest()
            debug("change detected in %r", src)
        else:
            debug("no change detected")
            return src_ts, old_hash, dst_handle, dst_ts, dst_hash
    debug("closing dest handle %r to directory %r", dst_handle, dirname(dst))
    win32file.FindCloseChangeNotification(dst_handle)
    function(src, dst)
    dst_ts = os.stat(dst).st_mtime
    debug("new destination %r timestamp is %r", dst, dst_ts)
    digest = sha256()
    with open(dst, 'r') as fd:
        digest.update(fd.read())
    dst_hash = digest.hexdigest()
    debug("new destination %r hash is %r", dst, dst_hash)
    dst_handle = win32file.FindFirstChangeNotification(
        dirname(dst), 0, win32con.FILE_NOTIFY_CHANGE_LAST_WRITE | win32con.FILE_NOTIFY_CHANGE_FILE_NAME,
    )
    debug("new change handle for %r is %r", dirname(dst), dst_handle)
    return src_ts, new_hash, dst_handle, dst_ts, dst_hash

if __name__ == '__main__':
    pickle_data = abspath(sys.argv[1])
    if exists(pickle_data):
        wd = tempfile.mkdtemp()
        data_file = join(wd, basename(pickle_data))
        pickle_data_ts = data_file_ts = pickle_data_hash = data_file_hash = None
        edit_handle = win32file.FindFirstChangeNotification(
            dirname(data_file), 0, win32con.FILE_NOTIFY_CHANGE_LAST_WRITE | win32con.FILE_NOTIFY_CHANGE_FILE_NAME,
        )
        change_handle = win32file.FindFirstChangeNotification(
            dirname(pickle_data), 0, win32con.FILE_NOTIFY_CHANGE_LAST_WRITE | win32con.FILE_NOTIFY_CHANGE_FILE_NAME,
        )
        pickle_data_ts, pickle_data_hash, edit_handle, data_file_ts, data_file_hash = update(
            (pickle_data, change_handle, pickle_data_ts, pickle_data_hash),
            (data_file, edit_handle, data_file_hash),
            pickle2text,
        )
        npp = subprocess.Popen([NPP, "-nosession", "-multiInst", "-lpython", data_file], shell=False)
        try:
            while 1:
                debug("wait for objects (%r, %r)", change_handle, edit_handle)
                result = win32event.WaitForMultipleObjects((change_handle, edit_handle), 0, 1000)
                npp.poll()
                if npp.returncode is not None:
                    info("npp exited with code %d", npp.returncode)
                    break
                debug("wait for multiple objects returned %r (WAIT_OBJECT_0 = %d, WAIT_TIMEOUT = %d)", result, win32con.WAIT_OBJECT_0, win32con.WAIT_TIMEOUT)
                if result == win32con.WAIT_TIMEOUT:
                    pass
                elif result >= win32con.WAIT_OBJECT_0 and result <= win32con.WAIT_OBJECT_0 + 1:
                    if result - win32con.WAIT_OBJECT_0 == 0:
                        # pickle file has been updated
                        debug("directory %r has changed", dirname(pickle_data))
                        if not exists(pickle_data):
                            warn("pickle file %r has been removed", pickle_data)
                            break
                        else:
                            pickle_data_ts, pickle_data_hash, edit_handle, data_file_ts, data_file_hash = update(
                                (pickle_data, change_handle, pickle_data_ts, pickle_data_hash),
                                (data_file, edit_handle, data_file_hash),
                                pickle2text,
                            )
                            win32file.FindNextChangeNotification(change_handle)
                    else:
                        # edit file has been updated
                        info("directory %r has changed", dirname(data_file))
                        if not exists(data_file):
                            warn("data file %r has been removed", data_file)
                            break
                        else:
                            data_file_ts, data_file_hash, change_handle, pickle_data_ts, pickle_data_hash = update(
                                (data_file, edit_handle, data_file_ts, data_file_hash),
                                (pickle_data, change_handle, pickle_data_hash),
                                text2pickle,
                            )
                            win32file.FindNextChangeNotification(edit_handle)
                else:
                    warn("unhandled result %r from wait for multiple objects", result)
        finally:
            try:
                win32file.FindCloseChangeNotification(edit_handle)
                win32file.FindCloseChangeNotification(change_handle)
            except:
                pass
            shutil.rmtree(wd)
            logging.shutdown()
