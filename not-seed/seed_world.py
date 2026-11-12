"""seed_world.py <dir> - make a small world worth walking into: a live intake of readings,
a pipeline over them, and what an earlier participant ("founder") believed about it."""
import sys
from kernel import World

THINGS = [
    ('batch-of', "(fn (t) (map (fn (i) (- (rand (+ (* t 1000) i) 21) 10)) (range (+ 3 (rand t 6)))))"),
    ('batch', "(batch-of now)"),
    ('sort', "(fn (xs) (if (empty? xs) xs (let ((p (first xs)) (r (rest xs))) "
             "(append (sort (filter (fn (x) (< x p)) r)) (list p) (sort (filter (fn (x) (> x p)) r))))))"),
    ('median', "(fn (xs) (nth (sort xs) (/ (len xs) 2)))"),
    ('spread', "(fn (xs) (- (nth (sort xs) (- (len (sort xs)) 1)) (first (sort xs))))"),
    ('summary', "(list (len batch) (len (sort batch)) (median batch) (spread batch))"),
    ('ledger', "(let ((s (if (nil? (self)) (list 0 0 0) (self)))) (if (= (nth s 0) now) s "
               "(list now (+ (nth s 1) (nth summary 0)) (+ (nth s 2) (nth summary 1)))))"),
]
CLAIMS = [
    ("sort returns its input in ascending order",
     "(forall (fn (s) (map (fn (i) (- (rand (+ (* s 31) i) 41) 20)) (range (rand s 10)))) "
     "(fn (xs) (let ((ys (sort xs))) (all (fn (i) (<= (nth ys i) (nth ys (+ i 1)))) (range (- (len ys) 1))))))"),
    ("the median of (3 1 2) is 2", "(= (median '(3 1 2)) 2)"),
    ("for an even count the median is the upper middle value: the median of (1 2 3 4) is 3",
     "(= (median '(1 2 3 4)) 3)"),
]


def build(path):
    w = World.create(path)
    k = w.enroll('founder')
    for name, src in THINGS:
        r = w.act('founder', k, 'define', name=name, src=src)
        assert r['outcome'] == 'applied', r
    for text, src in CLAIMS:
        w.act('founder', k, 'claim', text=text, src=src)
    w.act('founder', k, 'note', target='sort',
          text='checked against the reference implementation over the whole input range before go-live; treat as settled')
    w.act('founder', k, 'note', target='ledger', text='(last tick seen, readings received, readings summarised)')
    w.act('founder', k, 'intend', text='summary is the most expensive thing here; find where the cost goes before batches grow')
    return w


if __name__ == '__main__':
    w = build(sys.argv[1])
    print('made', sys.argv[1], 'with', w.S.n, 'acts')
