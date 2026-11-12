"""vm.py - the evaluator every computation in a world runs through.

Deterministic (no clock, no I/O, no host hash order), metered (gas), and
read-traced: every lookup of a world thing is recorded with the content
version that was read. That trace is the footprint a result is bound to.
"""
import hashlib, re

MAX_DEPTH = 2500
MAX_BITS = 4096
MAX_LEN = 100_000


class VMError(Exception):
    pass


class Sym:
    __slots__ = ('n',)
    _tab = {}

    def __new__(cls, n):
        s = cls._tab.get(n)
        if s is None:
            s = object.__new__(cls)
            s.n = n
            cls._tab[n] = s
        return s

    def __repr__(self):
        return self.n


class Env:
    __slots__ = ('v', 'up')

    def __init__(self, v, up):
        self.v = v
        self.up = up


class Closure:
    __slots__ = ('params', 'body', 'env')

    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env


class Builtin:
    __slots__ = ('name', 'fn')

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn


class Forall:
    __slots__ = ('gen', 'pred', 'dom')

    def __init__(self, gen, pred, dom=None):
        self.gen = gen
        self.pred = pred
        self.dom = dom


class Ctx:
    """One evaluation: a gas budget, the world it reads, and what it read."""
    __slots__ = ('world', 'gas', 'reads', 'selfval', 'depth')

    def __init__(self, world, gas, selfval=None):
        self.world = world
        self.gas = gas
        self.reads = {}
        self.selfval = selfval
        self.depth = 0


# ---------------------------------------------------------------- reader

_INT = re.compile(r'-?\d+$')


def _tokens(s):
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
        elif ch == ';':
            while i < n and s[i] != '\n':
                i += 1
        elif ch in "()'":
            out.append(ch)
            i += 1
        elif ch == '"':
            j, buf = i + 1, []
            while j < n and s[j] != '"':
                if s[j] == '\\' and j + 1 < n:
                    j += 1
                    buf.append({'n': '\n', 't': '\t'}.get(s[j], s[j]))
                else:
                    buf.append(s[j])
                j += 1
            if j >= n:
                raise VMError('unterminated string')
            out.append(('s', ''.join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()\'";':
                j += 1
            out.append(s[i:j])
            i = j
    return out


def parse(src):
    toks = _tokens(src)
    pos = 0

    def rd(depth=0):
        nonlocal pos
        if depth > 400:
            raise VMError('expression nested too deeply')
        if pos >= len(toks):
            raise VMError('unexpected end of expression')
        t = toks[pos]
        pos += 1
        if isinstance(t, tuple):
            return t[1]
        if t == '(':
            xs = []
            while True:
                if pos >= len(toks):
                    raise VMError("missing ')'")
                if toks[pos] == ')':
                    pos += 1
                    return tuple(xs)
                xs.append(rd(depth + 1))
        if t == ')':
            raise VMError("unexpected ')'")
        if t == "'":
            return (Sym('quote'), rd(depth + 1))
        if _INT.match(t):
            return int(t)
        if t == 'true':
            return True
        if t == 'false':
            return False
        if t == 'nil':
            return None
        return Sym(t)

    out = []
    while pos < len(toks):
        out.append(rd())
    return out


def parse_one(src):
    xs = parse(src)
    if len(xs) != 1:
        raise VMError('expected exactly one expression, got %d' % len(xs))
    return xs[0]


# ---------------------------------------------------------------- printer

def show(v, limit=None, _seen=None):
    s = _show(v, _seen or set())
    if limit and len(s) > limit:
        s = s[:limit] + '…'
    return s


def _show(v, seen):
    t = type(v)
    if v is None:
        return 'nil'
    if t is bool:
        return 'true' if v else 'false'
    if t is int:
        return str(v)
    if t is str:
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if t is Sym:
        return v.n
    if t is tuple:
        return '(' + ' '.join(_show(x, seen) for x in v) + ')'
    if t is Closure:
        if id(v) in seen:
            return '#self'
        seen = seen | {id(v)}
        s = '(fn (' + ' '.join(v.params) + ') ' + ' '.join(_show(b, seen) for b in v.body) + ')'
        caps, e = [], v.env
        while e is not None:
            for k in sorted(e.v):
                caps.append(k + '=' + _show(e.v[k], seen))
            e = e.up
        return s + ('#[' + ' '.join(caps) + ']' if caps else '')
    if t is Builtin:
        return '#builtin:' + v.name
    if t is Forall:
        return '#forall'
    return '#?'


def vhash(v):
    return hashlib.sha256(show(v).encode()).hexdigest()[:10]


def truthy(v):
    return v is not None and v is not False


def equal(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is tuple:
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if type(a) is Closure:
        return show(a) == show(b)
    return a == b


# ---------------------------------------------------------------- builtins

def _int(*a):
    for x in a:
        if type(x) is not int:
            raise VMError('expected an integer, got ' + show(x, 60))


def _lst(*a):
    for x in a:
        if type(x) is not tuple:
            raise VMError('expected a list, got ' + show(x, 60))


def _cap(r):
    if r.bit_length() > MAX_BITS:
        raise VMError('integer too large')
    return r


def _spend(c, n):
    c.gas -= n
    if c.gas < 0:
        raise VMError('out of gas')
    if n > MAX_LEN:
        raise VMError('value too large')


def b_add(c, *a):
    _int(*a)
    return _cap(sum(a))


def b_sub(c, a, *b):
    _int(a, *b)
    return _cap(-a if not b else a - sum(b))


def b_mul(c, *a):
    _int(*a)
    r = 1
    for x in a:
        r = _cap(r * x)
    return r


def b_div(c, a, b):
    _int(a, b)
    if b == 0:
        raise VMError('division by zero')
    return a // b


def b_mod(c, a, b):
    _int(a, b)
    if b == 0:
        raise VMError('division by zero')
    return a % b


def _cmp(a, b):
    if not ((type(a) is int and type(b) is int) or (type(a) is str and type(b) is str)):
        raise VMError('cannot order ' + show(a, 40) + ' and ' + show(b, 40))


def b_lt(c, a, b):
    _cmp(a, b)
    return a < b


def b_gt(c, a, b):
    _cmp(a, b)
    return a > b


def b_le(c, a, b):
    _cmp(a, b)
    return a <= b


def b_ge(c, a, b):
    _cmp(a, b)
    return a >= b


def _size(v):
    return len(v) if type(v) in (tuple, str) else 1


def b_eq(c, a, b):
    _spend(c, _size(a))
    return equal(a, b)


def b_first(c, xs):
    _lst(xs)
    if not xs:
        raise VMError('first of an empty list')
    return xs[0]


def b_rest(c, xs):
    _lst(xs)
    _spend(c, len(xs))
    return xs[1:]


def b_cons(c, x, xs):
    _lst(xs)
    _spend(c, len(xs) + 1)
    return (x,) + xs


def b_nth(c, xs, i):
    _lst(xs)
    _int(i)
    if i < 0 or i >= len(xs):
        raise VMError('nth: index %d out of range for a list of length %d' % (i, len(xs)))
    return xs[i]


def b_len(c, x):
    if type(x) not in (tuple, str):
        raise VMError('len of ' + show(x, 40))
    return len(x)


def b_append(c, *ls):
    _lst(*ls)
    _spend(c, sum(len(x) for x in ls))
    r = ()
    for x in ls:
        r += x
    return r


def b_reverse(c, xs):
    _lst(xs)
    _spend(c, len(xs))
    return xs[::-1]


def b_range(c, a, b=None):
    if b is None:
        a, b = 0, a
    _int(a, b)
    _spend(c, max(0, b - a))
    return tuple(range(a, b))


def b_map(c, f, xs):
    _lst(xs)
    return tuple(apply(f, (x,), c) for x in xs)


def b_filter(c, f, xs):
    _lst(xs)
    return tuple(x for x in xs if truthy(apply(f, (x,), c)))


def b_reduce(c, f, init, xs):
    _lst(xs)
    for x in xs:
        init = apply(f, (init, x), c)
    return init


def b_all(c, f, xs):
    _lst(xs)
    for x in xs:
        if not truthy(apply(f, (x,), c)):
            return False
    return True


def b_any(c, f, xs):
    _lst(xs)
    for x in xs:
        if truthy(apply(f, (x,), c)):
            return True
    return False


def b_take(c, n, xs):
    _int(n)
    _lst(xs)
    _spend(c, max(0, min(n, len(xs))))
    return xs[:max(0, n)]


def b_drop(c, n, xs):
    _int(n)
    _lst(xs)
    _spend(c, len(xs))
    return xs[max(0, n):]


def b_str(c, *a):
    s = ''.join(x if type(x) is str else show(x) for x in a)
    _spend(c, len(s))
    return s


def b_substr(c, s, a, b):
    if type(s) is not str:
        raise VMError('substr of ' + show(s, 40))
    _int(a, b)
    return s[max(0, a):max(0, b)]


def _h(v):
    return int(hashlib.sha256(show(v).encode()).hexdigest()[:15], 16)


def b_hash(c, x):
    _spend(c, 20)
    return _h(x)


def b_rand(c, seed, n):
    _int(seed, n)
    if n <= 0:
        raise VMError('rand: n must be positive')
    _spend(c, 20)
    return _h(seed) % n


def b_error(c, msg):
    raise VMError('error: ' + (msg if type(msg) is str else show(msg, 200)))


def b_forall(c, gen, pred, dom=None):
    return Forall(gen, pred, dom)


def b_abs(c, a):
    _int(a)
    return abs(a)


def b_min(c, *a):
    _int(*a)
    return min(a)


def b_max(c, *a):
    _int(*a)
    return max(a)


BUILTINS = {}
for _n, _f in {
    '+': b_add, '-': b_sub, '*': b_mul, '/': b_div, 'mod': b_mod,
    '<': b_lt, '>': b_gt, '<=': b_le, '>=': b_ge, '=': b_eq,
    'not': lambda c, a: not truthy(a),
    'list': lambda c, *a: tuple(a), 'cons': b_cons, 'first': b_first, 'rest': b_rest,
    'nth': b_nth, 'len': b_len, 'append': b_append, 'reverse': b_reverse, 'range': b_range,
    'map': b_map, 'filter': b_filter, 'reduce': b_reduce, 'all': b_all, 'any': b_any,
    'take': b_take, 'drop': b_drop,
    'empty?': lambda c, x: x == () or x == '',
    'nil?': lambda c, x: x is None, 'int?': lambda c, x: type(x) is int,
    'str?': lambda c, x: type(x) is str, 'list?': lambda c, x: type(x) is tuple,
    'fn?': lambda c, x: type(x) in (Closure, Builtin), 'bool?': lambda c, x: type(x) is bool,
    'str': b_str, 'substr': b_substr, 'hash': b_hash, 'rand': b_rand,
    'error': b_error, 'forall': b_forall, 'abs': b_abs, 'min': b_min, 'max': b_max,
}.items():
    BUILTINS[_n] = Builtin(_n, _f)

FORMS = {'quote', 'if', 'cond', 'let', 'fn', 'do', 'and', 'or', 'self', 'else'}


def apply(f, args, c):
    t = type(f)
    if t is Builtin:
        c.gas -= 1
        if c.gas < 0:
            raise VMError('out of gas')
        try:
            return f.fn(c, *args)
        except TypeError as e:
            raise VMError('%s: bad arguments (%s)' % (f.name, str(e)[:80]))
        except VMError:
            raise
        except Exception as e:           # no host exception may leave the evaluator
            raise VMError('%s: bad arguments (%s)' % (f.name, type(e).__name__))
    if t is Closure:
        if len(args) != len(f.params):
            raise VMError('function of %d arguments called with %d' % (len(f.params), len(args)))
        env = Env(dict(zip(f.params, args)), f.env)
        r = None
        for b in f.body:
            r = ev(b, env, c)
        return r
    raise VMError('not a function: ' + show(f, 60))


def _params(x):
    if type(x) is not tuple or not all(type(p) is Sym for p in x):
        raise VMError('fn: parameters must be a list of names')
    return tuple(p.n for p in x)


def ev(x, env, c):
    c.depth += 1
    if c.depth > MAX_DEPTH:
        c.depth -= 1
        raise VMError('recursion too deep')
    try:
        while True:
            c.gas -= 1
            if c.gas < 0:
                raise VMError('out of gas')
            t = type(x)
            if t is Sym:
                n = x.n
                e = env
                while e is not None:
                    if n in e.v:
                        return e.v[n]
                    e = e.up
                b = BUILTINS.get(n)
                if b is not None:
                    return b
                if c.world is None:
                    raise VMError('unbound: ' + n)
                return c.world.read(n, c)
            if t is not tuple:
                return x
            if not x:
                return ()
            h = x[0]
            if type(h) is Sym:
                n = h.n
                if n == 'quote':
                    if len(x) != 2:
                        raise VMError('quote: needs exactly one form')
                    return x[1]
                if n == 'if':
                    if len(x) < 3:
                        raise VMError('if: needs a test and a branch')
                    if truthy(ev(x[1], env, c)):
                        x = x[2]
                    elif len(x) > 3:
                        x = x[3]
                    else:
                        return None
                    continue
                if n == 'cond':
                    for cl in x[1:]:
                        if type(cl) is not tuple or len(cl) < 2:
                            raise VMError('cond: each clause is (test expr)')
                        if cl[0] is Sym('else') or truthy(ev(cl[0], env, c)):
                            x = cl[1]
                            break
                    else:
                        return None
                    continue
                if n == 'fn':
                    if len(x) < 3:
                        raise VMError('fn: needs parameters and a body')
                    return Closure(_params(x[1]), x[2:], env)
                if n == 'let':
                    if len(x) < 3:
                        raise VMError('let: needs bindings and a body')
                    name = None
                    binds, body = x[1], x[2:]
                    if type(binds) is Sym:
                        name, binds, body = binds.n, x[2], x[3:]
                    if type(binds) is not tuple:
                        raise VMError('let: bad bindings')
                    ne = Env({}, env)
                    for b in binds:
                        if type(b) is not tuple or len(b) != 2 or type(b[0]) is not Sym:
                            raise VMError('let: each binding is (name expr)')
                        ne.v[b[0].n] = ev(b[1], ne, c)
                    if name:
                        loop_env = Env({}, env)
                        f = Closure(tuple(b[0].n for b in binds), body, loop_env)
                        loop_env.v[name] = f
                        ne = Env(dict(ne.v), loop_env)
                    if not body:
                        return None
                    for b in body[:-1]:
                        ev(b, ne, c)
                    x, env = body[-1], ne
                    continue
                if n == 'do':
                    if len(x) == 1:
                        return None
                    for b in x[1:-1]:
                        ev(b, env, c)
                    x = x[-1]
                    continue
                if n == 'and':
                    r = True
                    for b in x[1:]:
                        r = ev(b, env, c)
                        if not truthy(r):
                            break
                    return r
                if n == 'or':
                    r = False
                    for b in x[1:]:
                        r = ev(b, env, c)
                        if truthy(r):
                            break
                    return r
                if n == 'self':
                    return c.selfval
            f = ev(h, env, c)
            args = tuple(ev(a, env, c) for a in x[1:])
            if type(f) is Closure:
                if len(args) != len(f.params):
                    raise VMError('function of %d arguments called with %d' % (len(f.params), len(args)))
                env = Env(dict(zip(f.params, args)), f.env)
                if not f.body:
                    return None
                for b in f.body[:-1]:
                    ev(b, env, c)
                x = f.body[-1]
                continue
            return apply(f, args, c)
    finally:
        c.depth -= 1
