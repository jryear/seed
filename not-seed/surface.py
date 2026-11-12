"""surface.py - what a participant meets. Nothing here is state: every answer is
computed from the world at the moment of asking, for whoever is asking."""
from vm import VMError, Ctx, parse_one, show, ev
from kernel import _define, ASK_GAS, SAMPLE_CAP, Refused

HELP = """\
You are inside a running world. It keeps computing whether or not anyone is here.

WHAT EXISTS
  things    named expressions the kernel evaluates. A thing that reads another is recomputed
            when that other changes. `now` is the world's clock; it advances by itself.
  claims    words plus a probe. Nobody can set a claim's standing: the kernel runs the probe and
            the result (holds / fails / error) is the standing. A probe that returns
            (forall gen pred) is sampled: gen maps an integer seed to an input, pred must be true
            of every input. (forall gen pred in?) also states the domain: a counterexample someone
            offers counts only if (in? x) is true; with no in?, only if pred answers false on it. The world keeps sampling on every tick, and it remembers every
            counterexample it has ever confirmed.
  amending  you may redefine anything. The kernel first tries your change in a copy of the world;
            if a claim that holds now would stop holding, the change is HELD instead of applied.
            A held amendment is not a failure, it is an open disagreement with a witness attached.
  notes, disputes, pursuits   words. They carry no weight in any verification; they are how
            participants leave interpretation, disagreement and unfinished intent in the world.

MOVES                                        (ex <move> ...)
  look [thing|cN|hN|pN]      what is here, or one thing closely, and what you could do about it
  eval '<expr>'              run an experiment against the live world (not recorded)
  suppose <name> '<expr>'    what would follow if <name> were defined so (not recorded)
  why <thing|cN>             what this currently rests on, and which acts put that there
  history [target]           what happened, most recent last
  define <name> '<expr>' [--on <definition>] [--for pN]
  claim "<words>" '<probe>' [--for pN]
  counter cN '<expr>'        offer a counterexample; the kernel runs it before believing you
  dispute cN "<why>"         disagree with a claim in words (norms are settled by an arbiter)
  retire cN "<why>"          the claim's author or an arbiter only
  retry hN | withdraw hN     for a held amendment (its author or an arbiter)
  note <target> "<words>"    intend "<what you are attempting>"    resolve pN "<how it ended>"
  enroll <name>              enter the world under a name

LANGUAGE   a small Lisp; integers, strings, lists, functions. Only false and nil are falsy.
  (fn (x y) body)  (if c a b)  (cond (c a) (else b))  (let ((a 1) (b 2)) body)
  (let loop ((i 0)) ... (loop (+ i 1)))  (do a b)  (and ..) (or ..)  'sym '(1 2 3)
  (self)  the previous value of the thing being evaluated (nil the first time)
  + - * / mod abs min max   < > <= >= = not     (/ is floor division; = is structural)
  list cons first rest nth len append reverse range take drop map filter reduce all any
  empty? nil? int? str? list? fn? bool?   str substr   hash (rand seed n)   error forall
  Evaluation is deterministic and metered; a thing or probe that runs out of gas is in error.
"""


def ago(S, tick):
    d = S.tick - tick
    return 'this tick' if d == 0 else '%d tick%s ago' % (d, '' if d == 1 else 's')


def strength(S, cl):
    if cl.standing != 'holds':
        return cl.standing
    if cl.forall:
        s = 'holds — survived %d remembered case%s and %d sample%s' % (
            len(cl.cases), '' if len(cl.cases) == 1 else 's', cl.checked, '' if cl.checked == 1 else 's')
        if cl.checked >= SAMPLE_CAP:
            s += ' (sampling budget spent)'
        return s + '; not proven'
    return 'holds — one execution of the probe'


def footprint(S, reads):
    out = []
    for k in sorted(reads):
        c = S.cells.get(k)
        out.append('%s@%s' % (k, c.dh if c else 'absent'))
    return ' '.join(out) or '(reads nothing in the world)'


def tensions(S):
    out = []
    for cl in S.claims.values():
        if cl.retired:
            continue
        if cl.standing != 'holds':
            out.append(('✗', cl.id, '%s %s since act %d — "%s" [%s]' % (cl.id, cl.standing, cl.since, cl.text, cl.author),
                        cl.detail))
        elif cl.disputes:
            d = cl.disputes[-1]
            out.append(('?', cl.id, '%s holds but is disputed by %s — "%s"' % (
                cl.id, ', '.join(sorted({x['by'] for x in cl.disputes})), cl.text), '%s: %s' % (d['by'], d['why'])))
    for h in S.held.values():
        if h.status == 'held':
            out.append(('⏸', h.id, '%s held — %s wants %s = %s' % (h.id, h.author, h.name, h.src[:60]), h.reason))
    for c in S.cells.values():
        if c.err:
            out.append(('!', c.name, '%s is in error' % c.name, c.err))
    for p in S.pursuits.values():
        if p.open:
            w = S.who[p.author]
            out.append(('◌', p.id, '%s open — %s: "%s"' % (p.id, p.author, p.text),
                        '%s last acted %s; touched: %s' % (p.author, ago(S, w.last_tick), ' '.join(p.things) or 'nothing yet')))
    return out


def brief(v, err, n=64):
    return ('! ' + err)[:n] if err else show(v, n)


def look(S, me, target=None):
    L = []
    if not target:
        T = tensions(S)
        L.append('world · tick %d · act %d · you are %s%s' % (
            S.tick, S.n, me, ' (arbiter)' if me in S.who and 'arbiter' in S.who[me].roles else ''))
        L.append('')
        L.append('unsettled (%d)' % len(T) if T else 'nothing is unsettled')
        for sym, tid, line, more in T:
            L.append('  %s %s' % (sym, line))
            if more:
                L.append('      %s' % more[:200])
        L.append('')
        L.append('things')
        for k in sorted(S.cells):
            c = S.cells[k]
            guards = [cl.id for cl in S.claims.values() if not cl.retired and k in cl.reads]
            L.append('  %-12s %s%s' % (k, brief(c.value, c.err), ('   ⟵ ' + ' '.join(guards)) if guards else ''))
        ok = [cl for cl in S.claims.values() if not cl.retired and cl.standing == 'holds']
        if ok:
            L.append('')
            L.append('claims that currently hold')
            for cl in ok:
                L.append('  %s "%s" [%s] — %s' % (cl.id, cl.text, cl.author, strength(S, cl)))
        others = [k for k in sorted(S.who) if k not in ('kernel', me)]
        if others:
            L.append('')
            L.append('others: ' + ', '.join('%s (last acted %s)' % (k, ago(S, S.who[k].last_tick)) for k in others))
        L.append('')
        L.append('→ look <anything named above> · eval · suppose · why · history · help')
        return '\n'.join(L)
    notes = [n for n in S.notes if n['target'] == target]
    if target in S.cells:
        c = S.cells[target]
        L.append('%s — a thing, defined by %s at act %d, definition %s' % (c.name, c.author, c.n, c.dh))
        L.append('  definition  %s' % c.src)
        L.append('  value       %s' % brief(c.value, c.err, 600))
        L.append('  cost        %d gas at last evaluation' % c.gas)
        L.append('  reads       %s' % (' '.join(sorted(c.reads)) or '—'))
        L.append('  read by     %s' % (' '.join(sorted(k for k, o in S.cells.items() if target in o.reads)) or '—'))
        for cl in S.claims.values():
            if not cl.retired and target in cl.reads:
                L.append('  %s %s "%s" [%s]' % (cl.id, cl.standing, cl.text, cl.author))
        for h in S.held.values():
            if h.status == 'held' and h.name == target:
                L.append('  %s held amendment by %s — %s' % (h.id, h.author, h.reason))
        aff = ["suppose %s '<expr>'" % target, "define %s '<expr>' --on %s" % (target, c.dh), 'why %s' % target,
               'claim "<words>" \'<probe>\'', 'note %s "<words>"' % target]
        if target == 'now':
            aff = ['why now']
    elif target in S.claims:
        cl = S.claims[target]
        L.append('%s — a claim by %s (act %d): "%s"' % (cl.id, cl.author, cl.n, cl.text))
        L.append('  probe      %s' % cl.src)
        if cl.retired:
            L.append('  RETIRED by %s at act %d: %s' % (cl.retired['by'], cl.retired['n'], cl.retired['why']))
        L.append('  standing   %s (since act %d)' % (strength(S, cl), cl.since))
        if cl.detail:
            L.append('  witness    %s' % cl.detail)
        L.append('  rests on   %s' % footprint(S, cl.reads))
        for k in cl.cases:
            L.append('  remembered case %s — confirmed as a counterexample at act %d (found by %s)' % (
                show(k['x'], 120), k['n'], k['by']))
        for d in cl.disputes:
            L.append('  disputed by %s (act %d): %s' % (d['by'], d['n'], d['why']))
        aff = ['why %s' % target, 'dispute %s "<why>"' % target, 'note %s "<words>"' % target]
        if cl.forall:
            aff.insert(0, "counter %s '<expr for a counterexample>'" % target)
        if me == cl.author or (me in S.who and S.may_arbitrate(me)):
            aff.append('retire %s "<why>"' % target)
        if cl.retired:
            aff = []
    elif target in S.held:
        h = S.held[target]
        L.append('%s — an amendment by %s (act %d), %s' % (h.id, h.author, h.n, h.status))
        L.append('  wants      %s = %s' % (h.name, h.src))
        L.append('  premise    %s at definition %s' % (h.name, h.on))
        L.append('  reason     %s' % h.reason)
        for b in h.blockers:
            cl = S.claims[b['claim']]
            L.append('  blocked by %s "%s" [%s]%s — would fail %s' % (
                cl.id, cl.text, cl.author, ' (since retired)' if cl.retired else '', b['detail']))
        aff = []
        if h.status == 'held':
            aff = ['look %s' % b['claim'] for b in h.blockers] + ['dispute %s "<why>"' % b['claim'] for b in h.blockers]
            if me == h.author or (me in S.who and S.may_arbitrate(me)):
                aff += ['retry %s' % h.id, 'withdraw %s' % h.id]
            aff.append("suppose %s '<a different expr>'" % h.name)
    elif target in S.pursuits:
        p = S.pursuits[target]
        w = S.who[p.author]
        L.append('%s — a pursuit by %s (act %d): "%s"' % (p.id, p.author, p.n, p.text))
        L.append('  %s' % ('open; %s last acted %s' % (p.author, ago(S, w.last_tick)) if p.open else
                          'closed by %s: %s' % (p.resolution['by'], p.resolution['text'])))
        for t in p.things:
            if t in S.claims:
                cl = S.claims[t]
                L.append('  %s %s — "%s"%s' % (t, 'retired' if cl.retired else cl.standing, cl.text,
                                               (' — ' + cl.detail) if cl.detail and not cl.retired else ''))
            elif t in S.held:
                h = S.held[t]
                L.append('  %s %s — %s = %s — %s' % (t, h.status, h.name, h.src[:70], h.reason))
        L.append('  acts made for it:')
        for e in S.chron:
            if e['kind'] == 'act' and e['n'] in p.trail:
                L.append('    act %d  %s' % (e['n'], e['text'][:150]))
        aff = ['history %s' % target, 'note %s "<words>"' % target, 'resolve %s "<how it ended>"' % target,
               '(add --for %s to any act that continues it)' % target]
    else:
        raise Refused('nothing here is called %r' % target)
    for n in notes:
        L.append('  note by %s (act %d): %s' % (n['by'], n['n'], n['text']))
    if aff:
        L.append('')
        L.append('→ ' + '\n→ '.join(aff))
    return '\n'.join(L)


def last_event(S, pred):
    for e in reversed(S.chron):
        if pred(e):
            return e
    return None


def why(S, target):
    L = []
    if target in S.claims:
        cl = S.claims[target]
        L.append('%s is "%s" — standing: %s' % (cl.id, cl.text, strength(S, cl)))
        e = last_event(S, lambda e: e['kind'] == 'standing' and e['about'] and e['about'][0] == cl.id)
        if e:
            L.append('  it became so at act %d (tick %d): %s' % (e['n'], e['tick'], e['text']))
            cause = last_event(S, lambda x: x['n'] == e['n'] and x['kind'] in ('act', 'applied', 'challenge'))
            if cause:
                L.append('  that act was: %s' % cause['text'])
            elif e['kind'] == 'standing':
                L.append('  no participant did that: the world found it while sampling on its own clock')
        reads = cl.reads
    elif target in S.cells:
        c = S.cells[target]
        L.append('%s = %s' % (c.name, brief(c.value, c.err, 200)))
        L.append('  defined as %s by %s at act %d' % (c.src[:200], c.author, c.n))
        reads = c.reads
    else:
        raise Refused('why works on a thing or a claim')
    L.append('  it rests on:')
    seen = set()

    def walk(reads, depth):
        for k in sorted(reads):
            c = S.cells.get(k)
            if c is None:
                L.append('  %s%s — absent' % ('  ' * depth, k))
                continue
            L.append('  %s%s@%s — %s at act %d' % ('  ' * depth, k, c.dh, c.author, c.n))
            if k not in seen and depth < 4:
                seen.add(k)
                walk(c.reads, depth + 1)
    walk(reads, 1)
    return '\n'.join(L)


def history(S, target=None, limit=40):
    ev_ = [e for e in S.chron if not target or target in e['about'] or e['who'] == target]
    L = ['act %-4d tick %-5d %-9s %s' % (e['n'], e['tick'], e['kind'], e['text'][:220]) for e in ev_[-limit:]]
    return '\n'.join(L) or 'nothing has happened%s' % (' to ' + target if target else '')


def experiment(S, src):
    c = Ctx(S.clone(), ASK_GAS)
    try:
        v = ev(parse_one(src), None, c)
        out = show(v, 4000)
    except VMError as e:
        out = '! ' + str(e)
    return '%s\n  (%d gas; read %s)' % (out, ASK_GAS - c.gas, footprint(S, c.reads))


def suppose(S, me, name, src):
    try:
        parse_one(src)
    except VMError as e:
        raise Refused('cannot read that expression: %s' % e)
    T = S.clone()
    cur = T.cells.get(name)
    T2, res = _define(T, me, name, src, cur.dh if cur else None, S.n)
    L = []
    if res['outcome'] == 'held':
        L.append('If %s were defined so, the kernel would HOLD it: %s' % (name, res['reason']))
        for b in res['blockers']:
            L.append('  %s "%s" would fail %s' % (b['claim'], S.claims[b['claim']].text, b['detail']))
        return '\n'.join(L)
    L.append('If %s were defined so, the kernel would apply it. What would follow:' % name)
    for k in sorted(T2.cells):
        a, b = S.cells.get(k), T2.cells[k]
        if a is None or a.vh != b.vh:
            L.append('  %s: %s  →  %s   (%d gas)' % (k, brief(a.value, a.err, 50) if a else 'absent', brief(b.value, b.err, 50), b.gas))
        elif a.gas != b.gas:
            L.append('  %s: same value, cost %d → %d gas' % (k, a.gas, b.gas))
    for k, cl in T2.claims.items():
        if not cl.retired and S.claims[k].standing != cl.standing:
            L.append('  %s "%s": %s → %s' % (k, cl.text, S.claims[k].standing, cl.standing))
    if len(L) == 1:
        L.append('  nothing observable changes')
    return '\n'.join(L)
