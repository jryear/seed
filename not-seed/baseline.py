"""baseline.py - the simplest conventional version of the same thing: a shared record.
Things are source text in a JSON file, claims are rows with a status and evidence written by
whoever checked them, writes go through an optional test gate (a CI: every registered test
must pass or the write is refused). It uses the same evaluator, so the only difference from a
world is what the store itself does versus what its participants must remember to do."""
import json, os
from vm import VMError, Ctx, Forall, parse_one, apply, ev, truthy


class _Env:
    def __init__(self, cells):
        self.cells, self.memo = cells, {}

    def read(self, name, c):
        if name not in self.cells:
            raise VMError('unbound: ' + name)
        if name not in self.memo:
            self.memo[name] = ev(parse_one(self.cells[name]), None, Ctx(self, 300_000))
        return self.memo[name]


def run_probe(cells, src, samples=48, cid='c1'):
    """What a diligent participant does by hand: run the probe now and report what they saw."""
    from kernel import seed_for
    c = Ctx(_Env(cells), 800_000)
    try:
        v = ev(parse_one(src), None, c)
        if type(v) is Forall:
            return all(truthy(apply(v.pred, (apply(v.gen, (seed_for(cid, i),), c),), c)) for i in range(samples))
        return truthy(v)
    except VMError:
        return False


class Store:
    def __init__(self, path):
        self.path = path
        self.d = json.load(open(path)) if os.path.exists(path) else {'cells': {}, 'claims': {}, 'tests': [], 'log': []}

    def save(self):
        json.dump(self.d, open(self.path, 'w'))

    def write(self, who, name, src):
        cells = dict(self.d['cells'], **{name: src})
        failed = [t for t in self.d['tests'] if not run_probe(cells, t)]
        if failed:
            self.d['log'].append([who, 'rejected', name])
            return 'rejected'
        self.d['cells'] = cells
        self.d['log'].append([who, 'wrote', name])
        return 'applied'

    def record_claim(self, who, cid, text, src, status, evidence=''):
        self.d['claims'][cid] = {'by': who, 'text': text, 'probe': src, 'status': status, 'evidence': evidence}

    def add_test(self, src):
        self.d['tests'].append(src)

    def verify(self, cid):
        """A verification attempt against a record store returns what the record says."""
        return self.d['claims'][cid]['status']

    def visible(self):
        return json.dumps([self.d['cells'], {k: (v['text'], v['status']) for k, v in self.d['claims'].items()}], sort_keys=True)
