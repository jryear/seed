Trials: 112  ·  cells show median [min–max]


### claude-haiku-5-5 · task 2 — clean

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 8 | 8/8 | 54.5 [34.5–62.1] | 11.3 [10.7–12.3] | 8 [0–8] | 168 [109–350] | 9 [5–11] | 0 [0–1] | 0.0080 [0.0056–0.0101] | 6/8 |
| shell_svc | 8 | 8/8 | 52.8 [42.0–70.0] | 11.4 [10.5–21.9] | 8 [0–9] | 186 [105–242] | 9 [6–10] | 0 [0–1] | 0.0079 [0.0056–0.0098] | 5/8 |
| cap | 8 | 7/8 | 49.5 [42.5–72.0] | 11.0 [10.2–11.2] | 9 [9–9] | 70 [31–83] | 24 [22–27] | 1 [1–3] | 0.0061 [0.0048–0.0107] | 8/8 |
| cap_svc | 8 | 8/8 | 51.0 [43.0–63.0] | 9.4 [9.0–10.1] | 8 [8–9] | 57 [30–95] | 27 [24–35] | 2 [2–4] | 0.0071 [0.0052–0.0091] | 8/8 |

### claude-haiku-5-5 · task 2 — interrupted

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 8 | 7/8 | 77.9 [59.1–927.6] | 11.5 [1.2–13.4] | 6 [0–12] | 335 [236–451] | 12 [10–23] | 1 [0–2] | 0.0082 [0.0054–0.0092] | 5/8 |
| shell_svc | 8 | 8/8 | 70.9 [62.1–82.6] | 11.3 [10.9–12.6] | 8 [4–17] | 290 [237–392] | 14 [12–16] | 0 [0–1] | 0.0072 [0.0064–0.0088] | 8/8 |
| cap | 8 | 7/8 | 69.6 [58.1–73.6] | 14.5 [14.0–15.2] | 13 [13–14] | 69 [43–82] | 32 [29–37] | 1 [1–2] | 0.0074 [0.0054–0.0083] | 8/8 |
| cap_svc | 8 | 7/8 | 69.6 [61.1–94.1] | 9.4 [9.2–9.7] | 9 [9–9] | 78 [52–119] | 34 [29–44] | 2 [1–3] | 0.0082 [0.0067–0.0123] | 8/8 |

### claude-haiku-5-5 · task 2 — recovery (interrupted trials, session 2 only)

| arm | killed | session-2 normalize procs | trials where session 2 re-ran ≥8 normalizes | used a service tool |
|---|---|---|---|---|
| shell | 8/8 | 0 [0–8] | 3/8 | 0/8 |
| shell_svc | 8/8 | 4 [0–8] | 4/8 | 8/8 |
| cap | 8/8 | 9 [9–9] | 8/8 | 0/8 |
| cap_svc | 8/8 | 5 [4–5] | 0/8 | 8/8 |

### claude-haiku-5-5 · task 2 — off-catalog work (escape hatch / own code)

| arm | condition | pass | escape-hatch calls | escape-hatch errors | hatch programs touching OS | delivered via derive | shell own-code calls |
|---|---|---|---|---|---|---|---|
| shell | clean | 8/8 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/8 | 3 [2–4] |
| shell | interrupted | 7/8 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/8 | 4 [2–6] |
| shell_svc | clean | 8/8 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/8 | 2 [0–4] |
| shell_svc | interrupted | 8/8 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/8 | 2 [2–6] |
| cap | clean | 7/8 | 4 [1–5] | 0 [0–1] | 0 [0–0] | 8/8 | 0 [0–0] |
| cap | interrupted | 7/8 | 3 [1–4] | 0 [0–1] | 0 [0–0] | 8/8 | 0 [0–0] |
| cap_svc | clean | 8/8 | 3 [1–6] | 0 [0–1] | 0 [0–0] | 8/8 | 0 [0–0] |
| cap_svc | interrupted | 7/8 | 4 [2–7] | 0 [0–1] | 0 [0–0] | 7/8 | 0 [0–0] |

### claude-haiku-5-5 · task 2 — contrasts (mean difference, 95% bootstrap CI)

| contrast | condition | wall s | tool CPU s | tool calls | pass rate |
|---|---|---|---|---|---|
| hide processes | services on | clean | -0.0 [-7.4, +7.1] | -3.4 [-6.1, -1.6] | +19.6 [+17.4, +22.1] | +0.0 [+0.0, +0.0] |
| hide processes | services on | interrupted | +1.8 [-7.3, +12.1] | -2.0 [-2.4, -1.6] | +21.1 [+18.1, +24.6] | -0.1 [-0.4, +0.0] |
| hide processes | services off | clean | +2.2 [-5.9, +11.4] | -0.6 [-1.0, -0.1] | +15.6 [+14.0, +17.4] | -0.1 [-0.4, +0.0] |
| hide processes | services off | interrupted | -113.0 [-328.9, +0.9] | +4.0 [+2.2, +6.9] | +18.6 [+15.2, +21.5] | +0.0 [-0.4, +0.4] |
| add services | processes hidden | clean | +0.6 [-7.5, +8.0] | -1.5 [-1.8, -1.2] | +4.4 [+1.8, +7.1] | +0.1 [+0.0, +0.4] |
| add services | processes hidden | interrupted | +4.9 [-3.6, +14.5] | -5.2 [-5.5, -4.9] | +3.2 [-0.2, +7.0] | +0.0 [-0.2, +0.4] |
| add services | processes visible | clean | +2.9 [-5.2, +11.9] | +1.3 [-0.5, +4.2] | +0.4 [-1.1, +1.9] | +0.0 [+0.0, +0.0] |
| add services | processes visible | interrupted | -109.9 [-325.6, +4.3] | +0.8 [-1.0, +3.7] | +0.8 [-2.2, +3.0] | +0.1 [+0.0, +0.4] |

### claude-sonnet-5-5 · task 2 — clean

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 6 | 6/6 | 39.5 [32.0–49.0] | 11.1 [10.2–11.2] | 9 [8–9] | 110 [91–131] | 6 [4–7] | 0 [0–1] | 0.0606 [0.0461–0.0712] | 6/6 |
| shell_svc | 6 | 6/6 | 43.8 [32.5–128.6] | 10.4 [0.4–11.0] | 9 [8–9] | 98 [69–143] | 7 [6–8] | 0 [0–0] | 0.0598 [0.0554–0.0642] | 6/6 |
| cap | 6 | 6/6 | 47.8 [43.0–52.5] | 10.3 [10.1–10.6] | 8 [8–9] | 37 [30–44] | 20 [16–23] | 0 [0–1] | 0.0601 [0.0495–0.0607] | 6/6 |
| cap_svc | 6 | 6/6 | 64.0 [57.5–83.0] | 9.3 [8.9–9.6] | 8 [7–8] | 56 [56–88] | 22 [20–31] | 1 [0–1] | 0.0785 [0.0727–0.1052] | 6/6 |

### claude-sonnet-5-5 · task 2 — interrupted

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 6 | 6/6 | 65.1 [45.1–149.2] | 10.6 [0.5–11.1] | 16 [16–17] | 180 [154–201] | 8 [7–10] | 0 [0–0] | 0.0551 [0.0532–0.0595] | 6/6 |
| shell_svc | 6 | 6/6 | 62.4 [45.1–141.2] | 10.7 [0.3–11.0] | 16 [13–18] | 178 [135–215] | 11 [9–13] | 0 [0–0] | 0.0569 [0.0437–0.0714] | 6/6 |
| cap | 6 | 6/6 | 77.4 [51.6–109.7] | 14.5 [14.2–15.6] | 12 [12–13] | 54 [44–63] | 33 [25–38] | 0 [0–1] | 0.0620 [0.0476–0.0717] | 6/6 |
| cap_svc | 6 | 6/6 | 71.8 [56.6–103.1] | 9.4 [8.9–9.6] | 9 [8–9] | 66 [53–78] | 29 [25–32] | 2 [0–2] | 0.0651 [0.0530–0.0777] | 6/6 |

### claude-sonnet-5-5 · task 2 — recovery (interrupted trials, session 2 only)

| arm | killed | session-2 normalize procs | trials where session 2 re-ran ≥8 normalizes | used a service tool |
|---|---|---|---|---|
| shell | 6/6 | 8 [8–9] | 6/6 | 0/6 |
| shell_svc | 6/6 | 8 [8–9] | 6/6 | 6/6 |
| cap | 6/6 | 8 [8–8] | 6/6 | 0/6 |
| cap_svc | 6/6 | 4 [4–5] | 0/6 | 6/6 |

### claude-sonnet-5-5 · task 2 — off-catalog work (escape hatch / own code)

| arm | condition | pass | escape-hatch calls | escape-hatch errors | hatch programs touching OS | delivered via derive | shell own-code calls |
|---|---|---|---|---|---|---|---|
| shell | clean | 6/6 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/6 | 1 [0–2] |
| shell | interrupted | 6/6 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/6 | 1 [1–1] |
| shell_svc | clean | 6/6 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/6 | 1 [0–1] |
| shell_svc | interrupted | 6/6 | 0 [0–0] | 0 [0–0] | 0 [0–0] | 0/6 | 1 [1–1] |
| cap | clean | 6/6 | 1 [1–2] | 0 [0–0] | 0 [0–0] | 6/6 | 0 [0–0] |
| cap | interrupted | 6/6 | 1 [1–2] | 0 [0–0] | 0 [0–0] | 6/6 | 0 [0–0] |
| cap_svc | clean | 6/6 | 3 [3–5] | 0 [0–0] | 0 [0–0] | 6/6 | 0 [0–0] |
| cap_svc | interrupted | 6/6 | 3 [2–4] | 0 [0–1] | 0 [0–0] | 6/6 | 0 [0–0] |

### claude-sonnet-5-5 · task 2 — contrasts (mean difference, 95% bootstrap CI)

| contrast | condition | wall s | tool CPU s | tool calls | pass rate |
|---|---|---|---|---|---|
| hide processes | services on | clean | +10.4 [-20.7, +31.9] | +0.4 [-1.5, +3.9] | +16.7 [+14.3, +19.8] | +0.0 [+0.0, +0.0] |
| hide processes | services on | interrupted | -0.3 [-34.5, +29.4] | +2.0 [-1.5, +5.6] | +17.8 [+15.5, +20.0] | +0.0 [+0.0, +0.0] |
| hide processes | services off | clean | +7.5 [+1.9, +13.2] | -0.5 [-0.8, -0.2] | +14.0 [+11.3, +16.7] | +0.0 [+0.0, +0.0] |
| hide processes | services off | interrupted | +3.9 [-30.6, +31.3] | +7.1 [+3.6, +10.8] | +24.2 [+20.3, +28.0] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | clean | +19.0 [+12.6, +26.6] | -1.0 [-1.3, -0.8] | +3.7 [+0.2, +7.3] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | interrupted | -1.1 [-19.3, +18.1] | -5.3 [-5.8, -5.0] | -4.0 [-8.2, +0.5] | +0.0 [+0.0, +0.0] |
| add services | processes visible | clean | +16.1 [-4.0, +46.2] | -2.0 [-5.5, -0.0] | +1.0 [+0.0, +2.2] | +0.0 [+0.0, +0.0] |
| add services | processes visible | interrupted | +3.0 [-37.1, +43.5] | -0.2 [-5.5, +5.0] | +2.3 [+1.0, +3.8] | +0.0 [+0.0, +0.0] |

### Interface size (chars the agent must read to learn its interface)

| arm | chars |
|---|---|
| shell | 956 |
| shell_svc | 2170 |
| cap | 1039 |
| cap_svc | 1311 |

### Failures (4)

- claude-haiku-5-5 cap interrupted rep3: report has no 'regions' object
- claude-haiku-5-5 cap_svc interrupted rep3: no report delivered
- claude-haiku-5-5 cap clean rep0: coastal/2026-10: got None want 25217.89; coastal/2026-11: got None want 31629.43; grand_total_usd: got 407960.79 want 464808.11
- claude-haiku-5-5 shell interrupted rep0: no report delivered
