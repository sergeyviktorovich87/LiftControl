#!/usr/bin/env python3
"""Root-owned broker. Database requests contain only a fixed operation and version."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

LIB = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('updater', LIB/'github-updater.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
STATUS = u.ROOT/'updates/host-update-status.json'
CURSOR = u.STATE/'bridge-cursor'


def atomic(path, data, mode):
    fd, name = tempfile.mkstemp(prefix='.bridge-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
            os.fchmod(out.fileno(),mode)
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_status(state, target='', request_id=0):
    enabled = subprocess.run(['systemctl','is-enabled','--quiet','liftcontrol-github-update.timer'],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0
    value = {'state':state,'target':target,'request_id':request_id,
             'updated':int(time.time()),'auto_enabled':enabled}
    atomic(STATUS,json.dumps(value),0o644)


def get_cursor():
    try:
        value = int(CURSOR.read_text())
        return max(0,value)
    except FileNotFoundError:
        return 0


def get_request(after):
    result = u.run(['docker','exec',u.api_container(),'python','manage.py',
                    'pending_system_update','--after',str(after)],
                   capture_output=True,timeout=20,text=True)
    request = json.loads(result.stdout.strip())
    if request is None:
        return None
    if not isinstance(request,dict) or type(request.get('id')) is not int or request['id'] <= after:
        raise ValueError('INVALID_BRIDGE_REQUEST')
    action,target = request.get('action'),request.get('target')
    if action == 'check' and target == '':
        return request
    if action == 'install':
        u.version(target)
        return request
    raise ValueError('INVALID_BRIDGE_ACTION')


def tick():
    cursor = get_cursor()
    # The same flock protects CLI, nightly timer and panel operations.
    with (u.STATE/'lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return
        request = get_request(cursor)
        if not request:
            try:
                previous = json.loads(STATUS.read_text())
                state,target = previous['state'],previous.get('target','')
                if state in ('checking','installing'):
                    state = 'failed'  # lock was released without terminal status
                if state == 'available' and u.version(target) <= u.version(u.health()):
                    state,target = 'current',''
                write_status(state,target,cursor)
            except (FileNotFoundError,ValueError,KeyError,TypeError):
                write_status('idle','',cursor)
            return
        action,target,request_id = request['action'],request['target'],request['id']
        # Consume before executing. An interrupted request is never replayed.
        atomic(CURSOR,str(request_id),0o600)
        write_status('checking' if action=='check' else 'installing',target,request_id)
        print('PANEL_UPDATE_REQUEST',request_id,action,target,flush=True)
        try:
            state,selected = u.update(check_only=action=='check',
                                      expected_target=target if action=='install' else None)
            write_status(state,selected,request_id)
            print('PANEL_UPDATE_RESULT',request_id,state,selected,flush=True)
        except Exception as exc:
            write_status('failed',target,request_id)
            print('PANEL_UPDATE_FAILED',request_id,type(exc).__name__,flush=True)
            raise


def main():
    if os.geteuid()!=0:
        raise SystemExit('Run as root')
    os.umask(0o077)
    for path,private in ((u.STATE,True),(STATUS.parent,False)):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode & (0o077 if private else 0o022):
            raise SystemExit('UNSAFE_BRIDGE_DIRECTORY')
    tick()


if __name__=='__main__':
    main()
