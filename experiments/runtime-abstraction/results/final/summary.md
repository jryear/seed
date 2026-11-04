Trials: 112  ·  models: claude-haiku-5-5, claude-sonnet-5-5  ·  cells show median [min–max]


### claude-haiku-5-5 — clean

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 8 | 8/8 | 40.3 [29.5–52.5] | 13.4 [12.0–14.3] | 8 [8–9] | 162 [107–227] | 6 [5–9] | 0 [0–0] | 0.0050 [0.0040–0.0067] | 8/8 |
| shell_svc | 8 | 8/8 | 43.8 [37.0–52.6] | 13.2 [12.3–14.1] | 8 [8–9] | 156 [123–229] | 8 [7–10] | 0 [0–1] | 0.0056 [0.0047–0.0074] | 8/8 |
| cap | 8 | 8/8 | 34.0 [27.5–41.0] | 12.4 [11.7–13.2] | 9 [9–9] | 19 [19–19] | 17 [14–19] | 1 [1–1] | 0.0031 [0.0022–0.0040] | 8/8 |
| cap_svc | 8 | 8/8 | 43.3 [36.0–73.0] | 10.5 [10.1–11.2] | 8 [8–9] | 19 [18–20] | 23 [22–25] | 1 [1–2] | 0.0050 [0.0045–0.0058] | 8/8 |

### claude-haiku-5-5 — interrupted

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 8 | 8/8 | 69.4 [54.6–80.2] | 13.9 [13.4–15.6] | 13 [7–16] | 365 [247–456] | 13 [9–14] | 0 [0–1] | 0.0068 [0.0049–0.0090] | 8/8 |
| shell_svc | 8 | 8/8 | 62.9 [55.6–72.7] | 13.3 [11.9–15.2] | 14 [7–19] | 286 [231–366] | 14 [11–15] | 0 [0–1] | 0.0057 [0.0049–0.0075] | 8/8 |
| cap | 8 | 8/8 | 52.1 [44.1–63.2] | 16.3 [15.7–17.0] | 13 [13–13] | 31 [31–31] | 27 [22–31] | 1 [1–1] | 0.0041 [0.0033–0.0053] | 8/8 |
| cap_svc | 8 | 8/8 | 58.6 [47.1–72.1] | 10.8 [10.2–11.1] | 9 [8–9] | 28 [27–30] | 30 [26–34] | 1 [1–1] | 0.0058 [0.0044–0.0075] | 8/8 |

### claude-haiku-5-5 — recovery (interrupted trials, session 2 only)

| arm | killed | session-2 normalize procs | trials where session 2 re-ran ≥8 normalizes | used a service tool |
|---|---|---|---|---|
| shell | 8/8 | 8 [0–8] | 6/8 | 0/8 |
| shell_svc | 8/8 | 8 [0–8] | 5/8 | 8/8 |
| cap | 8/8 | 9 [9–9] | 8/8 | 0/8 |
| cap_svc | 8/8 | 5 [5–6] | 0/8 | 8/8 |

### claude-haiku-5-5 — contrasts (mean difference, 95% bootstrap CI)

| contrast | condition | wall s | tool CPU s | tool calls | pass rate |
|---|---|---|---|---|---|
| hide processes | services on | clean | +0.9 [-5.6, +9.9] | -2.7 [-3.2, -2.2] | +15.1 [+14.1, +16.1] | +0.0 [+0.0, +0.0] |
| hide processes | services on | interrupted | -3.5 [-10.0, +2.9] | -2.8 [-3.6, -2.1] | +16.4 [+14.8, +18.2] | +0.0 [+0.0, +0.0] |
| hide processes | services off | clean | -6.2 [-12.3, -0.3] | -0.8 [-1.4, -0.3] | +10.1 [+8.9, +11.4] | +0.0 [+0.0, +0.0] |
| hide processes | services off | interrupted | -14.4 [-22.0, -6.7] | +2.1 [+1.5, +2.7] | +14.1 [+11.8, +16.5] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | clean | +10.6 [+4.1, +19.4] | -1.8 [-2.2, -1.4] | +6.1 [+5.0, +7.2] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | interrupted | +6.3 [-1.0, +13.3] | -5.6 [-5.9, -5.2] | +3.1 [+0.6, +5.8] | +0.0 [+0.0, +0.0] |
| add services | processes visible | clean | +3.5 [-2.5, +9.4] | +0.0 [-0.6, +0.6] | +1.1 [+0.0, +2.2] | +0.0 [+0.0, +0.0] |
| add services | processes visible | interrupted | -4.6 [-11.8, +2.9] | -0.6 [-1.5, +0.3] | +0.9 [-0.6, +2.5] | +0.0 [+0.0, +0.0] |

### claude-sonnet-5-5 — clean

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 6 | 6/6 | 36.3 [34.0–60.6] | 11.9 [1.9–23.4] | 9 [8–16] | 96 [78–113] | 5 [4–6] | 0 [0–1] | 0.0595 [0.0552–0.0621] | 6/6 |
| shell_svc | 6 | 6/6 | 43.5 [29.0–46.5] | 12.7 [11.9–23.3] | 9 [8–16] | 89 [73–113] | 6 [6–8] | 0 [0–1] | 0.0492 [0.0358–0.0636] | 6/6 |
| cap | 6 | 6/6 | 45.5 [37.5–54.0] | 12.5 [11.7–13.8] | 9 [8–9] | 19 [19–25] | 14 [14–21] | 1 [0–1] | 0.0355 [0.0351–0.0528] | 6/6 |
| cap_svc | 6 | 6/6 | 43.3 [39.5–49.0] | 11.3 [9.9–11.9] | 8 [8–8] | 18 [18–19] | 16 [15–18] | 1 [1–1] | 0.0396 [0.0368–0.0505] | 6/6 |

### claude-sonnet-5-5 — interrupted

| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | all execve | tool calls | tool errors | final-session cost $ | used provided workers |
|---|---|---|---|---|---|---|---|---|---|---|
| shell | 6 | 6/6 | 58.6 [33.6–85.1] | 12.1 [11.5–13.2] | 17 [16–17] | 170 [117–183] | 8 [5–10] | 0 [0–1] | 0.0544 [0.0386–0.0648] | 6/6 |
| shell_svc | 6 | 6/6 | 56.1 [41.1–70.1] | 11.6 [11.1–12.1] | 17 [16–17] | 176 [160–179] | 11 [11–12] | 0 [0–1] | 0.0391 [0.0372–0.0453] | 6/6 |
| cap | 6 | 6/6 | 53.4 [47.6–74.2] | 15.4 [14.9–18.9] | 12 [11–13] | 32 [30–37] | 20 [18–25] | 1 [0–2] | 0.0374 [0.0352–0.0456] | 6/6 |
| cap_svc | 6 | 6/6 | 44.4 [37.1–53.1] | 10.6 [10.1–11.5] | 8 [8–9] | 26 [26–27] | 17 [17–18] | 0 [0–1] | 0.0286 [0.0271–0.0305] | 6/6 |

### claude-sonnet-5-5 — recovery (interrupted trials, session 2 only)

| arm | killed | session-2 normalize procs | trials where session 2 re-ran ≥8 normalizes | used a service tool |
|---|---|---|---|---|
| shell | 6/6 | 9 [8–9] | 6/6 | 0/6 |
| shell_svc | 6/6 | 9 [8–9] | 6/6 | 6/6 |
| cap | 6/6 | 9 [8–9] | 6/6 | 0/6 |
| cap_svc | 6/6 | 4 [4–5] | 0/6 | 6/6 |

### claude-sonnet-5-5 — contrasts (mean difference, 95% bootstrap CI)

| contrast | condition | wall s | tool CPU s | tool calls | pass rate |
|---|---|---|---|---|---|
| hide processes | services on | clean | +3.2 [-2.2, +9.5] | -3.3 [-7.0, -1.0] | +9.3 [+8.3, +10.3] | +0.0 [+0.0, +0.0] |
| hide processes | services on | interrupted | -11.8 [-20.8, -2.3] | -0.9 [-1.4, -0.5] | +6.0 [+5.7, +6.5] | +0.0 [+0.0, +0.0] |
| hide processes | services off | clean | +5.5 [-4.1, +12.9] | +0.4 [-4.8, +5.6] | +10.0 [+8.3, +12.5] | +0.0 [+0.0, +0.0] |
| hide processes | services off | interrupted | +0.2 [-15.3, +15.8] | +4.3 [+2.9, +5.8] | +13.3 [+11.2, +15.8] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | clean | -2.4 [-7.5, +2.7] | -1.6 [-2.4, -0.8] | +0.8 [-1.7, +2.7] | +0.0 [+0.0, +0.0] |
| add services | processes hidden | interrupted | -12.8 [-22.0, -4.5] | -5.8 [-7.2, -4.5] | -3.8 [-5.8, -1.8] | +0.0 [+0.0, +0.0] |
| add services | processes visible | clean | -0.2 [-10.1, +7.8] | +2.1 [-3.5, +7.8] | +1.5 [+0.7, +2.3] | +0.0 [+0.0, +0.0] |
| add services | processes visible | interrupted | -0.8 [-16.9, +15.1] | -0.6 [-1.1, -0.1] | +3.5 [+2.3, +4.8] | +0.0 [+0.0, +0.0] |

### Interface size (chars the agent must read to learn its interface)

| arm | chars |
|---|---|
| shell | 956 |
| shell_svc | 2170 |
| cap | 1039 |
| cap_svc | 1311 |

### Failures (0)

