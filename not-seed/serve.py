"""serve.py - keeps one world running and lets participants reach it.
  python3 serve.py <world-dir> [--port 7070] [--door 7071] [--tick 3]
The main port is the same for everyone (name + key). The door port is the human's:
whatever arrives there acts as `human`."""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from kernel import World, Refused
import surface

ACTS = ('define', 'claim', 'counter', 'retire', 'dispute', 'note', 'intend', 'resolve', 'retry', 'withdraw', 'grant')


def say(res):
    o = res.get('outcome')
    if o == 'applied':
        return 'applied: %s is now definition %s' % (res['name'], res['dh'])
    if o == 'held':
        s = 'HELD as %s — %s' % (res['held'], res['reason'])
        for b in res['blockers']:
            s += '\n  %s would fail %s' % (b['claim'], b['detail'])
        return s + '\n→ look %s' % res['held']
    if 'claim' in res and o in ('holds', 'fails', 'error'):
        return '%s recorded; the kernel ran its probe: %s%s' % (res['claim'], o, (' — ' + res['detail']) if res['detail'] else '')
    if o == 'confirmed':
        return 'the kernel ran your input and confirms it: %s now %s' % (res['claim'], res['standing'])
    if o == 'rejected':
        return 'not accepted: %s' % res['detail']
    if 'pursuit' in res:
        return 'opened %s' % res['pursuit']
    return 'done'


def handle(w, q):
    op, me, key = q.get('op'), q.get('as'), q.get('key')
    if op == 'help':
        return surface.HELP
    if op == 'enroll':
        return 'you are %s. key: %s (saved in the world\'s keys/)' % (q.get('name'), w.enroll(q.get('name')))
    with w.lock:
        w.auth(me, key)
        S = w.S
        if op == 'look':
            return surface.look(S, me, q.get('target'))
        if op == 'why':
            return surface.why(S, q.get('target'))
        if op == 'history':
            return surface.history(S, q.get('target'))
        if op == 'eval':
            return surface.experiment(S, q.get('src') or '')
        if op == 'suppose':
            return surface.suppose(S, me, q.get('name'), q.get('src') or '')
        if op in ACTS:
            p = {k: v for k, v in q.items() if k not in ('op', 'as', 'key')}
            return say(w.act(me, key, op, **p))
    raise Refused('no such move: %s (try help)' % op)


def make_handler(w, human_key=None):
    class Hd(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='application/json'):
            b = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if human_key and self.path.split('?')[0] == '/':
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'door.html'), 'rb') as f:
                    return self._send(200, f.read(), 'text/html; charset=utf-8')
            if self.path == '/pulse':
                with w.lock:
                    S = w.S
                    return self._send(200, json.dumps({
                        'tick': S.tick, 'act': S.n, 'visible': S.visible_hash(), 'unsettled': len(surface.tensions(S)),
                        'names': sorted(S.cells) + sorted(S.claims) + sorted(S.held) + sorted(S.pursuits)}))
            self._send(404, '{}')

        def do_POST(self):
            try:
                q = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                if not isinstance(q, dict):
                    raise Refused('send a JSON object')
                if human_key:
                    q['as'], q['key'] = 'human', human_key
                out = {'ok': True, 'text': handle(w, q)}
            except Refused as e:
                out = {'ok': False, 'text': str(e)}
            except Exception as e:
                out = {'ok': False, 'text': 'the kernel could not do that: %s: %s' % (type(e).__name__, e)}
            self._send(200, json.dumps(out))
    return Hd


def main():
    a = sys.argv[1:]
    path = a[0]

    def opt(name, default):
        return int(a[a.index(name) + 1]) if name in a else default
    port, door, tick = opt('--port', 7070), opt('--door', 7071), opt('--tick', 3)
    w = World(path) if os.path.exists(os.path.join(path, 'acts.jsonl')) else World.create(path)
    with open(os.path.join(path, 'port'), 'w') as f:
        f.write(str(port))
    hk = open(os.path.join(path, 'keys', 'human.key')).read().strip()
    for p, h in ((port, make_handler(w)), (door, make_handler(w, hk))):
        srv = ThreadingHTTPServer(('127.0.0.1' if p == port else '0.0.0.0', p), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    print('world %s: %d acts replayed, tick %d; participants on :%d, human door on :%d' % (path, w.S.n, w.S.tick, port, door), flush=True)
    while True:
        time.sleep(tick)
        if tick:
            w.tick()


if __name__ == '__main__':
    t = threading.Thread(target=main)
    t.start()
    t.join()
