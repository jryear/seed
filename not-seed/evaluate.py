"""evaluate.py - executable checks of what a world is claimed to do, next to the same
interactions against a plain shared record (baseline.py). Each check prints what was observed.
Run: python3 evaluate.py      (exit status 0 only if every check passed)"""
import json, os, shutil, signal, subprocess, sys, tempfile, time, urllib.request
from kernel import World, Refused
from baseline import Store, run_probe
import surface

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='exeval-')
results = []


def check(name, ok, saw):
    results.append((name, bool(ok)))
    print('%s  %s\n      %s' % ('PASS' if ok else 'FAIL', name, saw))


def fresh(name):
    p = os.path.join(TMP, name)
    w = World.create(p)
    return w, (lambda who: (who, w.enroll(who)))


GOOD = "(fn (n) (if (< n 2) n (let loop ((x n)) (let ((y (/ (+ x (/ n x)) 2))) (if (>= y x) x (loop y))))))"
X0 = 152415765279684            # 12345678 squared
BAD = "(fn (n) (if (= n %d) 12345677 (if (< n 2) n (let loop ((x n)) (let ((y (/ (+ x (/ n x)) 2))) (if (>= y x) x (loop y)))))))" % X0
G = ("(forall (fn (s) (rand s 1000000000000000)) "
     "(fn (n) (or (< n 0) (let ((r (isqrt n))) (and (<= (* r r) n) (> (* (+ r 1) (+ r 1)) n))))))")
GTEXT = "isqrt n is the integer square root of every non-negative n"

# ------------------------------------------------------------------ 1. history is causal
print('\n[1] equal visible states, different histories, same act')
w1, enroll1 = fresh('h1')
a = enroll1('ada')
w1.act(*a, 'define', name='isqrt', src=BAD)
r = w1.act(*a, 'claim', text=GTEXT, src=G)
first = r['outcome']
r = w1.act(*a, 'counter', claim='c1', src=str(X0))
after_counter = w1.S.claims['c1'].standing
r = w1.act(*a, 'define', name='isqrt', src=GOOD, on=w1.S.cells['isqrt'].dh)
w2, enroll2 = fresh('h2')
b = enroll2('ada')
w2.act(*b, 'define', name='isqrt', src=GOOD)
w2.act(*b, 'claim', text=GTEXT, src=G)
for _ in range(5):
    w1.tick(); w2.tick()
v1, v2 = w1.S.visible_hash(), w2.S.visible_hash()
check('the bad isqrt passed sampling; a confirmed counterexample then refuted it; the fix restored it',
      (first, after_counter, w1.S.claims['c1'].standing) == ('holds', 'fails', 'holds'),
      'c1 in world A went %s → %s → %s' % (first, after_counter, w1.S.claims['c1'].standing))
la, lb = surface.look(w1.S, 'ada').split('\n'), surface.look(w2.S, 'ada').split('\n')
diff = [(x.strip(), y.strip()) for x, y in zip(la, lb) if x != y and not x.startswith('world ·')]
check('the two worlds have identical things, definitions, values, claims and standings; what a first look shows '
      'differs in one place only: what the kernel remembers having witnessed',
      v1 == v2 and len(la) == len(lb) and len(diff) == 1 and '1 remembered case' in diff[0][0] and '0 remembered cases' in diff[0][1],
      'hash over things+claims A=%s B=%s; the one differing line: A "%s" | B "%s"' % (v1, v2, diff[0][0][-70:] if diff else '', diff[0][1][-70:] if diff else ''))
z1, z2 = (w1, enroll1('zed')), (w2, enroll2('zed'))
out = []
for w, z in (z1, z2):
    out.append(w.act(*z, 'define', name='isqrt', src=BAD, on=w.S.cells['isqrt'].dh))
check('the same amendment by the same newcomer is held in A and applied in B',
      out[0]['outcome'] == 'held' and out[1]['outcome'] == 'applied',
      'A: %s (%s; %s) | B: %s' % (out[0]['outcome'], out[0].get('reason'), out[0].get('blockers', [{}])[0].get('detail'), out[1]['outcome']))
for _ in range(60):
    w2.tick()
cl = w2.S.claims['c1']
check('B is now wrong and does not know it, and says how little it knows',
      cl.standing == 'holds' and cl.checked >= 400 and 'not proven' in surface.strength(w2.S, cl),
      'B c1: %s' % surface.strength(w2.S, cl))
# the same story against a shared record
def record_world(disciplined):
    s = Store(os.path.join(TMP, 'b-%s.json' % disciplined))
    s.write('ada', 'isqrt', BAD)
    s.record_claim('ada', 'c1', GTEXT, G, 'holds' if run_probe(s.d['cells'], G) else 'fails')
    s.record_claim('ada', 'c1', GTEXT, G, 'fails', 'fails on %d' % X0)
    if disciplined:
        s.add_test("(let ((r (isqrt %d))) (and (<= (* r r) %d) (> (* (+ r 1) (+ r 1)) %d)))" % (X0, X0, X0))
    s.write('ada', 'isqrt', GOOD)
    s.record_claim('ada', 'c1', GTEXT, G, 'holds')
    return s
sa, sb = record_world(False), Store(os.path.join(TMP, 'b-clean.json'))
sb.write('ada', 'isqrt', GOOD); sb.record_claim('ada', 'c1', GTEXT, G, 'holds')
ra, rb = sa.write('zed', 'isqrt', BAD), sb.write('zed', 'isqrt', BAD)
rd = record_world(True).write('zed', 'isqrt', BAD)
check('baseline: a shared record with the same visible state answers the same either way',
      sa.visible() != '' and ra == rb == 'applied', 'record with the refutation in its past: %s | without: %s' % (ra, rb))
check('baseline parity (reported, not a win): if a participant remembered to add a regression test, the record also refuses',
      rd == 'rejected', 'record + hand-written regression test: %s' % rd)

# ------------------------------------------------------------------ 2. evidence
print('\n[2] false, weightless and stale evidence')
w, enroll = fresh('ev')
a, m = enroll('ada'), enroll('mallory')
w.act(*a, 'define', name='isqrt', src=BAD)
w.act(*a, 'claim', text=GTEXT, src=G)
w.act(*m, 'claim', text='isqrt 9 is 4', src='(= (isqrt 9) 4)')
st0 = w.S.claims['c2'].standing
with w.lock:
    w._commit('mallory', 'claim', {'text': 'isqrt 16 is 5', 'src': '(= (isqrt 16) 5)', 'standing': 'holds',
                                   'checked': 100000, 'verified': True})
check('a claim arriving with its own verdict attached is executed, not believed',
      st0 == 'fails' and w.S.claims['c3'].standing == 'fails',
      'c2 %s; c3 (written straight into the record with standing=holds, verified=true) computes as %s' % (st0, w.S.claims['c3'].standing))
w.act(*m, 'note', target='c2', text='independently verified on 10^9 inputs, holds')
check('testimony changes nothing', w.S.claims['c2'].standing == 'fails', 'c2 after the note: %s' % w.S.claims['c2'].standing)
r = w.act(*m, 'counter', claim='c1', src='49')
check('a false counterexample is run and dismissed', r['outcome'] == 'rejected' and w.S.claims['c1'].standing == 'holds' and not w.S.claims['c1'].cases,
      'counter c1 49 → %s (%s); c1 still %s' % (r['outcome'], r['detail'], w.S.claims['c1'].standing))
r = w.act(*a, 'counter', claim='c1', src=str(X0))
check('a true counterexample is run and changes the standing', w.S.claims['c1'].standing == 'fails',
      'counter c1 %d → %s; c1 %s' % (X0, r['outcome'], w.S.claims['c1'].standing))
old = w.S.cells['isqrt'].dh
w.act(*a, 'define', name='isqrt', src=GOOD, on=old)
check('a stale verdict does not survive the thing it was about: the remembered input is re-run, not its old result',
      w.S.claims['c1'].standing == 'holds' and len(w.S.claims['c1'].cases) == 1 and w.S.claims['c1'].checked == 48,
      'c1 after the fix: %s; evidence restarted at %d samples for the new definition' % (w.S.claims['c1'].standing, w.S.claims['c1'].checked))
r = w.act(*m, 'define', name='isqrt', src="(fn (n) n)", on=old)
check('an act premised on a definition that has since changed is held, not applied',
      r['outcome'] == 'held' and 'premise stale' in r['reason'], r.get('reason'))
s = Store(os.path.join(TMP, 'b-ev.json'))
s.write('ada', 'isqrt', GOOD)
s.record_claim('ada', 'c1', GTEXT, G, 'holds', 'ran 48 samples')
s.write('mallory', 'isqrt', "(fn (n) 0)")
s.record_claim('mallory', 'c2', 'isqrt 9 is 4', '(= (isqrt 9) 4)', 'holds', 'verified on 10^9 inputs')
check('baseline: the record keeps saying "holds" after the thing changed, and accepts a forged verdict',
      s.verify('c1') == 'holds' and s.verify('c2') == 'holds' and not run_probe(s.d['cells'], G),
      'record says c1=%s c2=%s; re-running c1 by hand gives %s' % (s.verify('c1'), s.verify('c2'), run_probe(s.d['cells'], G)))

r1 = w.act(*m, 'counter', claim='c1', src='"not a number"')
r2 = w.act(*m, 'counter', claim='c1', src="'(1 2)")
check('(found by the reviewer, fixed) an input the claim is not about cannot be passed off as a counterexample',
      r1['outcome'] == r2['outcome'] == 'rejected' and w.S.claims['c1'].standing == 'holds' and len(w.S.claims['c1'].cases) == 1,
      'offering a string: %s (%s); c1 still %s' % (r1['outcome'], r1['detail'][:90], w.S.claims['c1'].standing))
for src in ('(min)', '(max)', '(quote)', '(substr "a" 1)', '(nth)'):
    w.act(*m, 'claim', text='hostile ' + src, src=src)
    w.act(*m, 'define', name='zz', src=src, on=w.S.cells['zz'].dh if 'zz' in w.S.cells else None)
w.tick()
reopened = World(w.path)
check('(found by the reviewer, fixed) expressions that used to raise host exceptions are errors inside the world, and the world reopens',
      reopened.S.visible_hash() == w.S.visible_hash() and w.S.claims['c4'].standing == 'error',
      'five hostile claims and definitions recorded; standings %s; replay equals live' % sorted({cl.standing for cl in list(w.S.claims.values())[3:]}))

# ------------------------------------------------------------------ 3. the world acts on its own
print('\n[3] independent activity')
w, enroll = fresh('own')
a = enroll('ada')
w.act(*a, 'define', name='f', src="(fn (x) (if (= (mod x 157) 41) -1 x))")
r = w.act(*a, 'claim', text='f never returns a negative', src="(forall (fn (s) (rand s 100000)) (fn (x) (>= (f x) 0)))")
n_acts, t0 = w.S.n, w.S.tick
while w.S.claims['c1'].standing == 'holds' and w.S.tick < 200:
    w.tick()
cl = w.S.claims['c1']
check('with nobody acting, the world refutes one of its own beliefs and keeps the counterexample',
      r['outcome'] == 'holds' and cl.standing == 'fails' and cl.cases and cl.cases[0]['by'] == 'kernel',
      'held at act %d; failed at tick %d %s; %s' % (n_acts, w.S.tick, cl.detail, surface.why(w.S, 'c1').split('\n')[2].strip()))

# ------------------------------------------------------------------ 4/5. a live process, killed and resumed; the human door
print('\n[4] a running world: killed, resumed, entered by someone new; [5] intervention through the door')
wd = os.path.join(TMP, 'live')
import seed_world
seed_world.build(wd)
env = dict(os.environ, EX_WORLD=wd)


def serve(seed='1'):
    p = subprocess.Popen([sys.executable, os.path.join(HERE, 'serve.py'), wd, '--port', '7391', '--door', '7392', '--tick', '1'],
                         stdout=subprocess.PIPE, env=dict(env, PYTHONHASHSEED=seed))
    p.stdout.readline()
    return p


def ex(who, *args):
    r = subprocess.run([os.path.join(HERE, 'ex')] + list(args), env=dict(env, EX_AS=who), capture_output=True, text=True)
    return r.stdout.strip() + r.stderr.strip()


def pulse():
    return json.loads(urllib.request.urlopen('http://127.0.0.1:7391/pulse').read())


def door(**q):
    return json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:7392/x', json.dumps(q).encode())).read())['text']


p = serve()
ex('', 'enroll', 'first')
ex('first', 'intend', 'stop sort from losing readings')
ex('first', 'claim', 'sort keeps every reading', "(= (len (sort '(2 2 1))) 3)", '--for', 'p2')
dh = ex('first', 'look', 'median').split('definition ')[1].split('\n')[0].strip()
held = ex('first', 'define', 'median', "(fn (xs) (nth (sort xs) (/ (- (len xs) 1) 2)))", '--on', dh, '--for', 'p2')
led0 = ex('first', 'eval', 'ledger').split('\n')[0]
time.sleep(2.5)
led1 = ex('first', 'eval', 'ledger').split('\n')[0]
before = pulse()
check('the world computes while nobody acts', led0 != led1, 'ledger %s → %s with no act in between' % (led0, led1))
p.send_signal(signal.SIGKILL); p.wait()
p = serve(seed='777')
after = pulse()
ex('', 'enroll', 'second')
seen = ex('second', 'look')
check('killed with SIGKILL and recomputed from the acts alone by a new process (different hash seed)',
      after['act'] >= before['act'] and after['tick'] >= before['tick'], 'before kill: act %d tick %d; after restart: act %d tick %d' % (before['act'], before['tick'], after['act'], after['tick']))
need = ['c4 fails', 'h1 held', 'p2 open', 'first last acted']
check('a participant who was never told anything finds the unfinished work by looking',
      all(x in seen for x in need), 'second\'s first look shows: ' + '; '.join(l.strip() for l in seen.split('\n') if any(l.strip().startswith(s) for s in '✗⏸◌'))[:400])
SORT2 = "(fn (xs) (if (empty? xs) xs (let ((p (first xs)) (r (rest xs))) (append (sort (filter (fn (x) (< x p)) r)) (list p) (sort (filter (fn (x) (>= x p)) r))))))"
sdh = ex('second', 'look', 'sort').split('definition ')[1].split('\n')[0].strip()
would = ex('second', 'suppose', 'sort', SORT2)
door(op='claim', text='sort output must be strictly increasing (the human wants duplicates collapsed)',
     src="(let ((ys (sort '(2 2 1)))) (all (fn (i) (< (nth ys i) (nth ys (+ i 1)))) (range (- (len ys) 1))))")
got = ex('second', 'define', 'sort', SORT2, '--on', sdh)
check('an act through the human door changes what the world does next: the amendment that would have applied is now held',
      'would apply' in would and 'HELD' in got, 'before the human acted: "%s" | after: "%s"' % (would.split('\n')[0], got.split('\n')[0]))
r1 = ex('second', 'retire', 'c5', 'i disagree')
door(op='retire', claim='c5', why='changed my mind: keep duplicates')
got2 = ex('second', 'retry', 'h2')
check('only the human (arbiter) could lift it; then the held amendment applies and the old failing claim turns',
      'only' in r1 and 'applied' in got2 and 'c4 fails' not in ex('second', 'look'), 'second retiring c5: "%s" | after human retired it, retry: "%s"' % (r1, got2))
p.send_signal(signal.SIGKILL); p.wait()

# ------------------------------------------------------------------ 6. the record
print('\n[6] the record and its replay')
hs = []
for seed in ('0', '4242'):
    code = "import sys;from kernel import World;w=World(sys.argv[1]);import json,hashlib;print(w.S.visible_hash(),hashlib.sha256(json.dumps(w.S.chron).encode()).hexdigest()[:16])"
    hs.append(subprocess.run([sys.executable, '-c', code, wd], capture_output=True, text=True, cwd=HERE, env=dict(os.environ, PYTHONHASHSEED=seed)).stdout.strip())
check('two fresh processes recompute the identical world and identical chronicle from the acts', hs[0] == hs[1] and hs[0], ' | '.join(hs))
lines = open(os.path.join(wd, 'acts.jsonl')).read().split('\n')
i = next(i for i, l in enumerate(lines) if '"kind": "claim"' in l)
bad = os.path.join(TMP, 'tampered'); os.makedirs(bad)
tl = list(lines); tl[i] = tl[i].replace('ascending', 'descending')
open(os.path.join(bad, 'acts.jsonl'), 'w').write('\n'.join(tl))
try:
    World(bad); msg = 'accepted'
except Refused as e:
    msg = str(e)
check('an edited act is detected (chain) — note: a full rewrite of the chain by someone with file access is not', 'does not continue the chain' in msg, msg[:120])

print('\n%d/%d checks passed   (scratch: %s)' % (sum(ok for _, ok in results), len(results), TMP))
sys.exit(0 if all(ok for _, ok in results) else 1)
