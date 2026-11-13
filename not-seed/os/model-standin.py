"""Scripted stand-in for a model. It fills the model contract with a lookup
table so the machine can be exercised without one. It understands nothing.

Contract: JSON on stdin {"ask": str, "asked": [...]}; JSON on stdout with any of
  "say": str, "packages": [nixpkgs attribute names],
  "tool": {"name": str, "source": str}, "check": shell command that must succeed.
"""
import json, sys
ask = json.load(sys.stdin)["ask"].lower()
BIGGEST = '''#!/usr/bin/env python3
import os, sys
root = sys.argv[1] if len(sys.argv) > 1 else "."
sizes = []
for d, _, fs in os.walk(root):
    for f in fs:
        p = os.path.join(d, f)
        try: sizes.append((os.path.getsize(p), p))
        except OSError: pass
for s, p in sorted(sizes, reverse=True)[:10]:
    print(f"{s:>12}  {p}")
'''
if "video" in ask:
    out = {"packages": ["ffmpeg"], "check": "ffmpeg -version",
           "say": "(stand-in) video work needs ffmpeg"}
elif "biggest" in ask or "largest" in ask:
    out = {"packages": ["python3"], "tool": {"name": "biggest", "source": BIGGEST},
           "check": "biggest /etc | grep -q .",
           "say": "(stand-in) writing a tool `biggest <folder>`"}
elif "break" in ask:
    out = {"packages": ["hello"], "check": "false",
           "say": "(stand-in) a change whose check cannot pass"}
else:
    out = {"say": "(stand-in) I am a lookup table and do not know that one."}
print(json.dumps(out))
