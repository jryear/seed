"""kernel.py - a world.

The only authoritative record is the hash-chained list of acts (acts.jsonl).
Everything else - values, standings, held amendments, tensions - is recomputed
from the acts by executing them. Nothing a participant writes can state a
conclusion: a claim's standing is whatever its probe does when the kernel runs it.
"""
import copy, hashlib, json, os, re, secrets, sys, threading
import time as _time
from vm import (VMError, Sym, Ctx, Forall, BUILTINS, FORMS, parse_one, show, vhash,
                truthy, apply, ev)

sys.setrecursionlimit(200_000)
threading.stack_size(256 * 1024 * 1024)

CELL_GAS = 300_000
CLAIM_GAS = 800_000
ASK_GAS = 1_500_000
INIT_SAMPLES = 48      # samples a forall-claim must survive whenever its footprint moves
TICK_SAMPLES = 8       # further samples the world spends on it each tick
SAMPLE_CAP = 400
NAME = re.compile(r'[a-z][a-z0-9\-\?\!\*<>=/\+]*$')
RESERVED = {'now', 'true', 'false', 'nil'} | set(BUILTINS) | FORMS


def H(s, n=10):
    return hashlib.sha256(s.encode()).hexdigest()[:n]


def seed_for(cid, i):
    return int(H('%s:%d' % (cid, i), 15), 16)


class Rec:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class State:
    def __init__(self):
        self.n = 0
        self.tick = 0
        self.cells = {}
        self.claims = {}
        self.held = {}
        self.pursuits = {}
        self.notes = []
        self.who = {}
        self.chron = []
        self.ids = {'c': 0, 'h': 0, 'p': 0}

    def clone(self):
        t = State.__new__(State)
        t.n, t.tick = self.n, self.tick
        t.cells = {k: copy.copy(v) for k, v in self.cells.items()}
        t.claims = {}
        for k, v in self.claims.items():
            w = copy.copy(v)
            w.cases = list(v.cases)
            w.disputes = list(v.disputes)
            t.claims[k] = w
        t.held = {k: copy.copy(v) for k, v in self.held.items()}
        t.pursuits = {}
        for k, v in self.pursuits.items():
            w = copy.copy(v)
            w.trail = list(v.trail)
            t.pursuits[k] = w
        t.notes = list(self.notes)
        t.who = {}
        for k, v in self.who.items():
            w = copy.copy(v)
            w.roles = set(v.roles)
            t.who[k] = w
        t.chron = list(self.chron)
        t.ids = dict(self.ids)
        return t

    # ---- the world as the evaluator sees it
    def read(self, name, c):
        cell = self.cells.get(name)
        if cell is None:
            c.reads[name] = None
            raise VMError('unbound: ' + name)
        if cell.busy:
            raise VMError('cycle through ' + name)
        if cell.dirty:
            self.eval_cell(cell)
        c.reads[name] = cell.vh
        if cell.err:
            raise VMError(('%s is in error: %s' % (name, cell.err))[:300])
        return cell.value

    def eval_cell(self, cell):
        cell.busy = True
        c = Ctx(self, CELL_GAS, cell.value)
        try:
            cell.value = ev(cell.expr, None, c)
            cell.err = None
        except VMError as e:
            cell.err = str(e)[:300]
        except Exception as e:
            cell.err = 'evaluator fault: ' + type(e).__name__
        cell.busy = False
        cell.dirty = False
        cell.reads = c.reads
        cell.gas = CELL_GAS - c.gas
        cell.vh = H('!' + cell.err) if cell.err else vhash(cell.value)

    def touch(self, names):
        dirty = set(names)
        grew = True
        while grew:
            grew = False
            for cell in self.cells.values():
                if cell.name not in dirty and any(r in dirty for r in cell.reads):
                    dirty.add(cell.name)
                    grew = True
        for nm in dirty:
            if nm in self.cells and nm != 'now':
                self.cells[nm].dirty = True

    def moved(self, reads):
        for k, v in reads.items():
            cell = self.cells.get(k)
            if (cell.vh if cell else None) != v:
                return True
        return False

    def settle(self):
        for nm in sorted(self.cells):
            if self.cells[nm].dirty:
                self.eval_cell(self.cells[nm])
        for cid in list(self.claims):
            cl = self.claims[cid]
            if not cl.retired and (cl.standing is None or self.moved(cl.reads)):
                self.check(cl)

    # ---- claims
    @staticmethod
    def _test(v, x, c):
        try:
            return (truthy(apply(v.pred, (x,), c)), '')
        except VMError as e:
            if 'out of gas' in str(e):
                raise
            return (False, ' (probe raised: %s)' % str(e)[:120])

    def check(self, cl, extra=0):
        old = cl.standing
        c = Ctx(self, CLAIM_GAS)
        st, det = 'holds', ''
        try:
            v = ev(cl.expr, None, c)
            if type(v) is Forall:
                cl.forall = True
                if not extra:
                    for k in cl.cases:
                        ok, msg = self._test(v, k['x'], c)
                        if not ok:
                            st = 'fails'
                            det = 'on remembered case %s%s' % (show(k['x'], 160), msg)
                            break
                    cl.checked = 0
                if st == 'holds':
                    i, end = cl.checked, cl.checked + (extra or INIT_SAMPLES)
                    try:
                        while i < end:
                            x = apply(v.gen, (seed_for(cl.id, i),), c)
                            ok, msg = self._test(v, x, c)
                            if not ok:
                                if not any(show(k['x']) == show(x) for k in cl.cases):
                                    cl.cases.append({'x': x, 'by': 'kernel', 'n': self.n, 'tick': self.tick})
                                st = 'fails'
                                det = 'on sampled input %s%s' % (show(x, 160), msg)
                                break
                            i += 1
                    except VMError as e:
                        if 'out of gas' not in str(e) or i == 0:
                            raise
                        cl.gaslimited = True
                    cl.checked = i
            else:
                cl.forall = False
                if not truthy(v):
                    st = 'fails'
                    det = 'probe evaluated to ' + show(v, 120)
        except VMError as e:
            st, det = 'error', str(e)[:300]
        except Exception as e:
            st, det = 'error', 'evaluator fault: ' + type(e).__name__
        if extra:
            cl.reads.update(c.reads)
        else:
            cl.reads = c.reads
        cl.detail = det
        if st != old:
            cl.standing = st
            cl.since = self.n
            self.event('standing', '%s: %s → %s%s' % (cl.id, old or 'new', st, (' — ' + det) if det else ''),
                       [cl.id] + sorted(cl.reads))

    def event(self, kind, text, about=(), who='kernel'):
        self.chron.append({'n': self.n, 'tick': self.tick, 'kind': kind, 'who': who,
                           'text': text, 'about': list(about)})

    def nid(self, k):
        self.ids[k] += 1
        return '%s%d' % (k, self.ids[k])

    def may_arbitrate(self, who):
        return 'arbiter' in self.who[who].roles

    def visible_hash(self):
        """What a participant sees of the things and the open claims - not how it got there."""
        cells = [(k, v.dh, v.vh) for k, v in sorted(self.cells.items())]
        claims = [(k, v.text, v.src, v.standing) for k, v in sorted(self.claims.items()) if not v.retired]
        return H(json.dumps([cells, claims]), 16)


# ---------------------------------------------------------------- acts

def _define(S, who, name, src, on, n, hid=None):
    """Try an amendment in a copy of the world; adopt the copy only if no standing claim breaks."""
    cur = S.cells.get(name)
    held = S.held.get(hid) if hid else None
    if cur and on != cur.dh:
        reason = 'premise stale: %s is at definition %s (act %d, by %s), not %s' % (
            name, cur.dh, cur.n, cur.author, on)
        blockers = []
    else:
        T = S.clone()
        cell = T.cells.get(name)
        expr = parse_one(src)
        if cell is None:
            cell = T.cells[name] = Rec(name=name, value=None, vh=None, reads={}, gas=0, err=None,
                                       busy=False, dirty=True)
        cell.expr, cell.src, cell.dh, cell.author, cell.n = expr, src, H(show(expr)), who, n
        T.touch([name])
        T.settle()
        blockers = [{'claim': cid, 'detail': T.claims[cid].detail or T.claims[cid].standing}
                    for cid, cl in S.claims.items()
                    if not cl.retired and cl.standing == 'holds' and T.claims[cid].standing != 'holds']
        if not blockers:
            if hid:
                T.held[hid].status = 'applied'
            T.event('applied', '%s %s %s → %s' % (who, 'amended' if cur else 'made', name, cell.dh),
                    [name] + ([hid] if hid else []), who)
            return T, {'outcome': 'applied', 'name': name, 'dh': cell.dh}
        reason = 'would break ' + ', '.join(b['claim'] for b in blockers)
    if held is None:
        hid = S.nid('h')
        held = S.held[hid] = Rec(id=hid, author=who, name=name, src=src, on=on, n=n, status='held')
    held.reason, held.blockers = reason, blockers
    S.event('held', '%s: %s wants to %s %s — %s' % (hid, held.author, 'amend' if cur else 'make', name, reason),
            [hid, name] + [b['claim'] for b in blockers], who)
    return S, {'outcome': 'held', 'held': hid, 'reason': reason, 'blockers': blockers}


def apply_act(S, a):
    """Deterministic: (state, act) -> (state, result). Replay calls exactly this."""
    S.n = a['n']
    who, kind, p = a['as'], a['kind'], a['p']
    res = {'outcome': 'ok'}
    if kind == 'tick':
        S.tick += 1
        now = S.cells['now']
        now.value, now.vh = S.tick, vhash(S.tick)
        S.touch(['now'])
        S.settle()
        for cl in S.claims.values():        # the world keeps trying to refute what it believes
            if not cl.retired and cl.forall and cl.standing == 'holds' and cl.checked < SAMPLE_CAP:
                S.check(cl, extra=TICK_SAMPLES)
        return S, res
    if kind == 'genesis':
        S.who['kernel'] = Rec(kh=None, roles=set(), last_n=0, last_tick=0)
        S.who['human'] = Rec(kh=p['human'], roles={'arbiter', 'root'}, last_n=0, last_tick=0)
        S.cells['now'] = Rec(name='now', expr=0, src='0', dh='-', author='kernel', n=a['n'], value=0,
                             vh=vhash(0), reads={}, gas=0, err=None, busy=False, dirty=False)
        S.event('act', 'the world begins', [], 'kernel')
        return S, res
    me = S.who.get(who)
    if me:
        me.last_n, me.last_tick = a['n'], S.tick
    pur = p.get('for')
    if pur and pur in S.pursuits:
        S.pursuits[pur].trail.append(a['n'])
    if kind == 'enroll':
        S.who[p['name']] = Rec(kh=p['kh'], roles=set(), last_n=a['n'], last_tick=S.tick)
        S.event('act', '%s enters the world' % p['name'], [], p['name'])
    elif kind == 'define':
        S.event('act', '%s proposes %s = %s' % (who, p['name'], p['src'][:100]), [p['name']], who)
        S, res = _define(S, who, p['name'], p['src'], p.get('on'), a['n'])
        if pur and res.get('held'):
            S.pursuits[pur].things.append(res['held'])
    elif kind == 'retry':
        h = S.held[p['held']]
        S.event('act', '%s retries %s' % (who, h.id), [h.id, h.name], who)
        S, res = _define(S, h.author, h.name, h.src, h.on, a['n'], hid=h.id)
    elif kind == 'withdraw':
        S.held[p['held']].status = 'withdrawn'
        S.event('act', '%s withdraws %s' % (who, p['held']), [p['held']], who)
    elif kind == 'claim':
        cid = S.nid('c')
        cl = S.claims[cid] = Rec(id=cid, author=who, text=p['text'], src=p['src'], expr=parse_one(p['src']),
                                 n=a['n'], cases=[], disputes=[], standing=None, detail='', reads={},
                                 checked=0, forall=False, retired=None, since=a['n'], gaslimited=False)
        S.event('act', '%s claims %s: "%s"' % (who, cid, p['text'][:100]), [cid], who)
        S.check(cl)
        res = {'outcome': cl.standing, 'claim': cid, 'detail': cl.detail}
        if pur:
            S.pursuits[pur].things.append(cid)
    elif kind == 'counter':
        cl = S.claims[p['claim']]
        c = Ctx(S, ASK_GAS)
        try:
            x = ev(parse_one(p['src']), None, c)
            v = ev(cl.expr, None, c)
            ok, msg = S._test(v, x, c)
            # An offered input is only a counterexample if it is an input the claim is about:
            # inside the claim's stated domain, or - with no domain stated - one the probe can
            # actually answer. (Inputs the world samples itself come from the claim's own generator.)
            if not ok and v.dom is not None and not truthy(apply(v.dom, (x,), c)):
                ok, msg = True, 'outside the domain the claim states'
            elif not ok and v.dom is None and msg:
                ok, msg = True, 'the probe cannot be run on it%s; the claim states no domain that admits it' % msg
        except (VMError, AttributeError) as e:
            S.event('challenge', '%s challenged %s but the challenge could not be run: %s' % (who, cl.id, e),
                    [cl.id], who)
            return S, {'outcome': 'rejected', 'detail': str(e)}
        if ok:
            S.event('challenge', '%s offered %s against %s; the kernel ran it — not a '
                    'counterexample%s' % (who, show(x, 100), cl.id, (' (' + msg + ')') if msg else ''), [cl.id], who)
            res = {'outcome': 'rejected', 'detail': msg or 'the probe passes on that input'}
        else:
            if not any(show(k['x']) == show(x) for k in cl.cases):
                cl.cases.append({'x': x, 'by': who, 'n': a['n'], 'tick': S.tick})
            S.event('challenge', '%s gave %s a counterexample the kernel confirmed: %s%s' % (
                who, cl.id, show(x, 100), msg), [cl.id], who)
            S.check(cl)
            res = {'outcome': 'confirmed', 'claim': cl.id, 'standing': cl.standing}
    elif kind == 'retire':
        cl = S.claims[p['claim']]
        cl.retired = {'by': who, 'n': a['n'], 'why': p.get('why', '')}
        S.event('act', '%s retires %s: %s' % (who, cl.id, p.get('why', '')), [cl.id], who)
    elif kind == 'dispute':
        S.claims[p['claim']].disputes.append({'by': who, 'n': a['n'], 'why': p['why']})
        S.event('act', '%s disputes %s: %s' % (who, p['claim'], p['why'][:160]), [p['claim']], who)
    elif kind == 'note':
        S.notes.append({'n': a['n'], 'tick': S.tick, 'by': who, 'target': p['target'], 'text': p['text']})
        S.event('act', '%s notes on %s: %s' % (who, p['target'], p['text'][:160]), [p['target']], who)
    elif kind == 'intend':
        pid = S.nid('p')
        S.pursuits[pid] = Rec(id=pid, author=who, text=p['text'], n=a['n'], open=True, trail=[], things=[],
                              resolution=None)
        S.event('act', '%s opens %s: %s' % (who, pid, p['text'][:160]), [pid], who)
        res = {'outcome': 'ok', 'pursuit': pid}
    elif kind == 'resolve':
        pu = S.pursuits[p['pursuit']]
        pu.open, pu.resolution = False, {'by': who, 'n': a['n'], 'text': p['text']}
        S.event('act', '%s closes %s: %s' % (who, pu.id, p['text'][:160]), [pu.id], who)
    elif kind == 'grant':
        S.who[p['name']].roles.add(p['role'])
        S.event('act', '%s grants %s the role %s' % (who, p['name'], p['role']), [], who)
    return S, res


# ---------------------------------------------------------------- the world on disk

class Refused(Exception):
    pass


class World:
    def __init__(self, path):
        self.path = path
        self.logf = os.path.join(path, 'acts.jsonl')
        self.S = State()
        self.head = 'origin'
        self.lock = threading.RLock()
        if os.path.exists(self.logf):
            self._replay()

    @staticmethod
    def create(path):
        os.makedirs(os.path.join(path, 'keys'), exist_ok=True)
        if os.path.exists(os.path.join(path, 'acts.jsonl')):
            raise Refused('a world already exists at ' + path)
        key = secrets.token_hex(8)
        kf = os.path.join(path, 'keys', 'human.key')
        with open(kf, 'w') as f:
            f.write(key)
        os.chmod(kf, 0o600)
        w = World(path)
        w._commit('kernel', 'genesis', {'human': H(key, 32)})
        return w

    @staticmethod
    def _digest(rec):
        return H(json.dumps({k: rec[k] for k in ('n', 'as', 'kind', 'p', 't', 'prev')}, sort_keys=True), 32)

    def _replay(self):
        with open(self.logf) as f:
            lines = f.read().split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        for i, line in enumerate(lines):
            try:
                rec = json.loads(line)
                good = (rec['prev'] == self.head and rec['n'] == self.S.n + 1 and rec['h'] == self._digest(rec))
            except Exception:
                good = False
            if not good:
                raise Refused('acts.jsonl line %d does not continue the chain; the record has been altered '
                              'or damaged. Refusing to compute a world from it.' % (i + 1))
            self.S, _ = apply_act(self.S, rec)
            self.head = rec['h']

    def _commit(self, who, kind, p):
        rec = {'n': self.S.n + 1, 'as': who, 'kind': kind, 'p': p, 't': int(_time.time()), 'prev': self.head}
        rec['h'] = self._digest(rec)
        with open(self.logf, 'a') as f:
            f.write(json.dumps(rec, sort_keys=True) + '\n')
            f.flush()
            if kind != 'tick':
                os.fsync(f.fileno())
        self.head = rec['h']
        self.S, res = apply_act(self.S, rec)
        return res

    def tick(self):
        with self.lock:
            return self._commit('kernel', 'tick', {})

    def auth(self, who, key):
        me = self.S.who.get(who)
        if me is None:
            raise Refused('nobody called %r has entered this world (enroll first)' % who)
        if me.kh is None or H(key or '', 32) != me.kh:
            raise Refused('that key does not open %r' % who)

    def enroll(self, name):
        with self.lock:
            if not NAME.match(name or '') or name in self.S.who:
                raise Refused('the name %r is taken or not usable' % name)
            key = secrets.token_hex(8)
            kf = os.path.join(self.path, 'keys', name + '.key')
            with open(kf, 'w') as f:
                f.write(key)
            os.chmod(kf, 0o600)
            self._commit(name, 'enroll', {'name': name, 'kh': H(key, 32)})
            return key

    def act(self, who, key, kind, **p):
        """Validate against the present, then record, then execute. Only well-formed acts are recorded."""
        with self.lock:
            self.auth(who, key)
            S = self.S
            p = {k: v for k, v in p.items() if v is not None}
            allowed = {'define': {'name', 'src', 'on', 'for'}, 'claim': {'text', 'src', 'for'},
                       'counter': {'claim', 'src', 'for'}, 'retire': {'claim', 'why'},
                       'dispute': {'claim', 'why'}, 'note': {'target', 'text', 'for'}, 'intend': {'text'},
                       'resolve': {'pursuit', 'text'}, 'retry': {'held'}, 'withdraw': {'held'},
                       'grant': {'name', 'role'}}
            if kind not in allowed:
                raise Refused('no such act: ' + str(kind))
            p = {k: v for k, v in p.items() if k in allowed[kind]}   # anything else a caller sends is dropped
            for k, v in p.items():
                if type(v) is not str or len(v) > 20_000:
                    raise Refused('%s must be text of reasonable size' % k)
            if 'src' in p:
                try:
                    parse_one(p['src'])
                except VMError as e:
                    raise Refused('cannot read that expression: %s' % e)
            if p.get('for') and not (p['for'] in S.pursuits and S.pursuits[p['for']].open):
                raise Refused('%s is not an open pursuit' % p['for'])

            def claim():
                cl = S.claims.get(p.get('claim'))
                if cl is None or cl.retired:
                    raise Refused('%s is not a standing claim here' % p.get('claim'))
                return cl

            def held():
                h = S.held.get(p.get('held'))
                if h is None or h.status != 'held':
                    raise Refused('%s is not a held amendment' % p.get('held'))
                if h.author != who and not S.may_arbitrate(who):
                    raise Refused('%s belongs to %s' % (h.id, h.author))
                return h

            if kind == 'define':
                name = p.get('name', '')
                if not NAME.match(name) or name in RESERVED or 'src' not in p:
                    raise Refused('%r cannot be used as the name of a thing' % name)
                cur = S.cells.get(name)
                if cur and 'on' not in p:
                    raise Refused('%s already exists (definition %s). To amend it, say which definition you '
                                  'are amending: on=%s' % (name, cur.dh, cur.dh))
            elif kind == 'claim':
                if not p.get('text') or 'src' not in p:
                    raise Refused('a claim needs words and a probe')
            elif kind == 'counter':
                if not claim().forall:
                    raise Refused('only a forall-claim can be given a counterexample; dispute this one instead')
                if 'src' not in p:
                    raise Refused('give an expression that evaluates to the counterexample')
            elif kind == 'retire':
                cl = claim()
                if cl.author != who and not S.may_arbitrate(who):
                    raise Refused('only %s or an arbiter can retire %s; you can dispute it' % (cl.author, cl.id))
            elif kind == 'dispute':
                claim()
                if not p.get('why'):
                    raise Refused('say why')
            elif kind == 'note':
                if not p.get('target') or not p.get('text'):
                    raise Refused('a note needs a target and words')
            elif kind == 'intend':
                if not p.get('text'):
                    raise Refused('say what you are attempting')
            elif kind == 'resolve':
                pu = S.pursuits.get(p.get('pursuit'))
                if pu is None or not pu.open:
                    raise Refused('%s is not an open pursuit' % p.get('pursuit'))
                if not p.get('text'):
                    raise Refused('say how it ended')
            elif kind in ('retry', 'withdraw'):
                held()
            elif kind == 'grant':
                if 'root' not in S.who[who].roles:
                    raise Refused('only the human can grant roles')
                if p.get('name') not in S.who or p.get('role') != 'arbiter':
                    raise Refused('grant <someone present> arbiter')
            return self._commit(who, kind, p)
