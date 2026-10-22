"""Real GUI/systemd fault checks. Root in WSL; loopback only, no production units."""
import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from procon_mock_server import ProconMockServer, MockHandler
from deadline_stress_test import request, audit_evidence, FIXTURE
ROOT = Path(__file__).resolve().parents[2]
RELEASE = Path('/home/hexa/release/http-fix-20261016')
VARIANTS = {'A': ('production', 8775), 'B': ('B', 8777), 'H2': ('H2', 8776)}
INJECTOR = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int blocked = -1;
ssize_t send(int fd, const void *data, size_t size, int flags) {
    static ssize_t (*actual)(int,const void*,size_t,int);
    if (!actual) actual = dlsym(RTLD_NEXT, "send");
    if (fd == blocked) { errno = EAGAIN; return -1; }
    const char *path = getenv("HEXA_TEST_FAULT");
    if (path && size > 10 && !memcmp(data, "POST /?", 7)) {
        FILE *file = fopen(path, "r");
        int mode = file ? fgetc(file) : 0;
        if (file) fclose(file);
        if (mode == 'm') {
            ssize_t sent = actual(fd, data, 10, flags);
            if (sent > 0) {
                blocked = fd;
                file = fopen(path, "w");
                if (file) { fprintf(file, "blocked: sent=%zd", sent); fclose(file); }
            }
            return sent;
        }
    }
    return actual(fd, data, size, flags);
}
"""


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def read_json(path):
    return json.loads(path.read_text())


class FaultServer(ThreadingHTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(22)
        if self.tls:
            if self.armed and (not self.injected or self.scenario == 'near_deadline'):
                self.injected += 1
                self.faults.append(dict(kind=self.scenario, start_ns=time.time_ns(),
                    start_monotonic_ns=time.monotonic_ns(), deadline=self.app.current_ends_at))
                if self.scenario != 'tls_close':
                    time.sleep(5.6)
                connection.close()
                raise OSError('Local injected TLS fault')
            try:
                connection = self.context.wrap_socket(connection, server_side=True)
            except Exception:
                connection.close()
                raise
        return connection, address


class FaultHandler(MockHandler):
    def do_POST(self):
        if self.server.scenario == 'lost_ack' and self.path.startswith('/?'):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            receipt = time.time_ns()
            status, body = self.server.app.handle_post_actions(payload)
            self.server.faults.append(dict(kind='lost_ack', receipt_ns=receipt,
                validation_ns=time.time_ns(), status=status, response=body, request=payload))
            time.sleep(16)
            self.close_connection = True
            return
        super().do_POST()

    def do_GET(self):
        super().do_GET()
        events = self.server.app.request_log
        if (self.server.scenario in ('tls_retry', 'tls_close', 'near_deadline') and events
                and events[-1]['path'] == '/' and events[-1]['status'] == 200
                and 'day' in events[-1]['response']):
            self.server.armed = True


def gui_key(port):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    connection.request('GET', '/')
    page = connection.getresponse().read().decode()
    connection.close()
    return re.search(r'nonce="([a-f0-9]{64})"', page).group(1)


def status(port, key):
    return request(port, 'GET', '/status', key=key)['body']


def run_case(output, home, variant, port, key, binary, context, scenario):
    directory = output / variant / scenario
    directory.mkdir(parents=True)
    fixture = read_json(ROOT / FIXTURE)
    days = 4 if scenario == 'normal' else 2 if scenario == 'recovery' else 1
    fixture['daySteps'] = fixture['daySteps'][:days]
    fixture_path = directory / 'fixture.json'
    fixture_path.write_text(json.dumps(fixture))
    day_seconds = 8 if scenario == 'near_deadline' else 25 if scenario == 'lost_ack' else 18
    app = ProconMockServer(str(fixture_path), 18, day_seconds)
    server = FaultServer(('127.0.0.1', 0), FaultHandler)
    server.app, server.context, server.scenario = app, context, scenario
    server.armed, server.injected, server.faults = False, 0, []
    server.tls = scenario in ('tls_retry', 'tls_close', 'near_deadline')
    fault_file = home / 'fault'
    fault_file.write_text('mid' if scenario == 'mid_send' else '')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'{"https" if server.tls else "http"}://127.0.0.1:{server.server_port}'
    result = dict(variant=variant, scenario=scenario, status='FAIL')
    last = None
    recovery = None
    try:
        assert not status(port, key)['running']
        assert request(port, 'POST', '/start', dict(mode='execute', backend='procon',
            confirmed=True, url=url, token=app.token), key=key)['status'] == 200
        last = status(port, key)
        unit_pid = int(command(['systemctl','show',f'hexa-http-test-{variant.lower()}', '-p','MainPID','--value']).strip())
        children = Path(f'/proc/{unit_pid}/task/{unit_pid}/children').read_text().split()
        assert len(children) == 1, children
        child = children[0]
        assert Path(f'/proc/{child}/exe').resolve() == binary.resolve()
        (directory/'process.json').write_text(json.dumps(dict(pid=child,
            executable=str(Path(f'/proc/{child}/exe').resolve()),
            command=Path(f'/proc/{child}/cmdline').read_bytes().replace(b'\0',b' ').decode(),
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),indent=2))
        limit = time.monotonic() + 18 + days * day_seconds + 40
        stopped = False
        while time.monotonic() < limit:
            last = status(port,key)
            if scenario == 'recovery' and app.day_plans and not stopped:
                assert request(port,'POST','/stop',dict(confirmed=True),key=key)['status']==200
                stopped = True
            if not last['running']:
                break
            time.sleep(.1)
        assert last and not last['running'], 'GUI client did not stop'
        session = Path(last['session'])
        (directory/'client.log').write_text(last['log'])
        state = read_json(session/'session.json')
        operations_path = session.parent/'log/operations.jsonl'
        operations = [json.loads(line) for line in operations_path.read_text().splitlines()]
        shutil.copy2(operations_path,directory/'operations.jsonl')
        diagnostics = [event for event in operations if event['operation']=='http-transport']
        if scenario in ('normal','tls_retry','recovery'):
            if scenario == 'recovery':
                assert stopped and last['exit_code'] == 130
                environment = dict(os.environ, PROCON_TOKEN=app.token)
                with (directory/'recover.log').open('w') as log:
                    recovery = subprocess.Popen([str(binary),'recover','--base-url',url,'--execute',
                        '--session-dir',str(session),'--log-dir',str(directory/'recover-operations'),
                        '--threads','8','--safety-seconds','3'],env=environment,stdout=log,stderr=log)
                    assert recovery.wait(timeout=65) == 0
                state = read_json(session/'session.json')
            else:
                assert last['exit_code'] == 0,last
            until = time.monotonic()+3
            while not app.match_completed and time.monotonic()<until:
                with app.lock: app.step_day_if_needed()
                time.sleep(.02)
            assert app.match_completed
            timings = audit_evidence(state,app.history,app.request_log,days,0)
            result['timings'] = timings
            if scenario=='tls_retry':
                assert server.injected==1
                assert any('requestStarted=false' in event['stopReason'] and event['submissionAttempted'] is False for event in diagnostics)
                assert any(event['operation']=='daily-submit' and event['result']=='retry-scheduled' for event in operations)
        else:
            posts = [event for event in app.request_log if event['method']=='POST' and event['path']=='/']
            assert not posts,posts
            if scenario=='near_deadline':
                assert server.injected==1
                assert not any(event['result']=='retry-scheduled' and event['operation']=='daily-submit' for event in operations)
                assert diagnostics and diagnostics[-1]['submissionAttempted'] is False
            else:
                assert state['submissions'][-1]['submissionAttempted'] is None
                assert 'RecoveryRequired' in last['log']
                if scenario=='lost_ack':
                    assert len(server.faults)==1 and server.faults[0]['response']['valid'] is True
                    assert app.day_revisions=={0:1}
                if scenario=='mid_send':
                    assert fault_file.read_text()=='blocked: sent=10'
                    assert any('requestStarted=true' in event['stopReason'] for event in diagnostics)
                if scenario=='tls_close':
                    assert server.injected==1
                    assert any('requestStarted=false' in event['stopReason'] for event in diagnostics)
                before = dict(app.day_revisions)
                environment = dict(os.environ,PROCON_TOKEN=app.token)
                recovery = subprocess.run([str(binary),'recover','--base-url',url.replace('https:', 'http:') if False else url,
                    '--execute','--session-dir',str(session),'--log-dir',str(directory/'recover-operations')],
                    env=environment,capture_output=True,text=True,timeout=20) if not server.tls else None
                if recovery is not None:
                    (directory/'recover.log').write_text(recovery.stdout+recovery.stderr)
                    assert 'RecoveryRequired' in recovery.stdout
                    assert app.day_revisions==before
                assert len([entry for entry in app.request_log if entry['method']=='POST' and entry['path']=='/'])==0
            assert last['exit_code'] != 0
        assert sum(event['method']=='POST' and event['path']=='/agent' for event in app.request_log)==1
        (directory/'session.json').write_text(json.dumps(state,indent=2))
        result.update(status='PASS',client_exit=last['exit_code'],faults=len(server.faults))
    except Exception as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        if status(port,key)['running']:
            request(port,'POST','/stop',dict(confirmed=True),key=key)
        server.shutdown()
        server.server_close()
        (directory/'http.json').write_text(json.dumps(app.request_log,indent=2))
        (directory/'faults.json').write_text(json.dumps(server.faults,indent=2))
        (directory/'history.json').write_text(json.dumps(app.history,indent=2))
        (directory/'result.json').write_text(json.dumps(result,indent=2))
        print(variant,scenario,result['status'],result.get('error',''),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',nargs='+',default=['normal','tls_retry','tls_close','lost_ack','mid_send','near_deadline','recovery'])
    parser.add_argument('--variants',nargs='+',default=list(VARIANTS))
    args=parser.parse_args()
    output=Path(tempfile.mkdtemp(prefix='http-gui-audit-',dir=ROOT/'results'))
    home_root=Path(tempfile.mkdtemp(prefix='http-gui-audit-',dir='/home/hexa'))
    home_root.chmod(0o755)
    print(output,flush=True)
    (home_root/'inject.c').write_text(INJECTOR)
    command(['gcc','-shared','-fPIC',str(home_root/'inject.c'),'-ldl','-o',str(home_root/'inject.so')])
    cert=home_root/'ca.pem'; key_file=home_root/'key.pem'
    command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=localhost',
        '-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(key_file),'-out',str(cert)])
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key_file)
    account=pwd.getpwnam('hexa')
    def variant_run(variant):
        suffix,port=VARIANTS[variant];binary=RELEASE/f'hexa_udon_{suffix}_httpfix'
        home=home_root/variant;home.mkdir();os.chown(home,account.pw_uid,account.pw_gid)
        fault=home/'fault';fault.touch();os.chown(fault,account.pw_uid,account.pw_gid)
        unit=f'hexa-http-test-{variant.lower()}'
        assert command(['systemctl','show',unit,'-p','ActiveState','--value']).strip()!='active'
        launch=['systemd-run',f'--unit={unit}','--collect','--uid=hexa',f'--setenv=HOME={home}',
            f'--setenv=LD_PRELOAD={home_root}/inject.so',f'--setenv=HEXA_TEST_FAULT={fault}',
            '--property=MemoryMax=3G','--property=CPUAffinity=0-7',
            f'--property=BindReadOnlyPaths={cert}:/etc/ssl/certs/ca-certificates.crt',
            f'--working-directory={ROOT}','/usr/bin/python3','-B',str(ROOT/'gui.py'),
            '--binary',str(binary),'--port',str(port)]
        command(launch)
        try:
            for _ in range(50):
                try: key=gui_key(port);break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('GUI did not open')
            (output/f'{variant}-unit.txt').write_text(command(['systemctl','show',unit,'-p','ExecStart','-p','MainPID','-p','ActiveState']))
            return [run_case(output,home,variant,port,key,binary,context,case) for case in args.cases]
        finally:
            subprocess.run(['systemctl','stop',unit],check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(variant_run,args.variants))
    (output/'summary.json').write_text(json.dumps(results,indent=2))
    return int(any(result['status']!='PASS' for group in results for result in group))


if __name__=='__main__':
    sys.exit(main())
