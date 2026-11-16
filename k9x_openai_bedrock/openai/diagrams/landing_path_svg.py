# Generates the landing page's request-path diagram (lego blocks, Streams-style, own content).
C = {"sdk": "#cbd5e1", "k9": "#34d399", "model": "#c4b5fd", "tool": "#22d3ee", "ext": "#94a3b8", "gate": "#fbbf24"}
out = []
def block(x, y, w, h, color, title, sub, studs=3, bold=False, fill="#0e1729"):
    gap = w / (studs + 1)
    for i in range(studs):
        sx = x + gap * (i + 1) - 11
        out.append(f'<rect x="{sx:.0f}" y="{y-7}" width="22" height="9" rx="3" fill="{fill}" stroke="{color}" stroke-width="1.6"/>')
    glow = ' filter="url(#gl)"' if bold else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{color}" stroke-width="{2.4 if bold else 1.6}"{glow}/>')
    cx = x + w / 2
    out.append(f'<text x="{cx:.0f}" y="{y + h/2 - 2:.0f}" fill="#f1f5f9" font-size="{16 if bold else 15}" font-weight="700" text-anchor="middle">{title}</text>')
    out.append(f'<text x="{cx:.0f}" y="{y + h/2 + 18:.0f}" fill="{color}" font-size="12" text-anchor="middle">{sub}</text>')
def flow(d, color, label=None, lx=0, ly=0, anchor="middle"):
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#ar)"/>')
    if label:
        out.append(f'<text x="{lx}" y="{ly}" fill="#94a3b8" font-size="11.5" text-anchor="{anchor}">{label}</text>')
def gate(x, y, n):
    out.append(f'<circle cx="{x}" cy="{y}" r="12" fill="#0b1220" stroke="{C["gate"]}" stroke-width="2"/>')
    out.append(f'<text x="{x}" y="{y+4}" fill="{C["gate"]}" font-size="11.5" font-weight="700" text-anchor="middle">{n}</text>')

# Shield band around everything the agent touches
out.append(f'<rect x="250" y="150" width="860" height="330" rx="20" fill="rgba(251,191,36,.045)" stroke="{C["gate"]}" stroke-dasharray="6 6"/>')
out.append(f'<text x="270" y="174" fill="{C["gate"]}" font-size="12.5" font-weight="700">k9x Shield + Zero Trust: every crossing is a checkpoint</text>')

block(40, 46, 170, 70, C["ext"], "Visitor", "zip code · role", studs=2)
block(300, 46, 360, 70, C["k9"], "K9-AIF orchestrator adapter", "OpenAIAgentsOrchestratorAdapter", studs=4, bold=True)
block(760, 46, 300, 70, C["k9"], "Answer + receipt", "every check, in order", studs=3)
block(330, 230, 300, 84, C["sdk"], "OpenAI Agents SDK", "Runner · WeatherAgent (YAML)", studs=4, bold=True)
block(760, 230, 300, 84, C["model"], "K9 Model Router", "eligibility first · tool_calling", studs=3)
block(300, 390, 170, 66, C["tool"], "lookup_zip", "zip → place", studs=2)
block(500, 390, 200, 66, C["tool"], "current_weather", "zip → conditions", studs=2)
block(790, 390, 240, 66, C["model"], "Local model", "OpenAI-compatible API", studs=3, fill="#111b30")
block(40, 390, 210, 66, C["ext"], "Public services", "zippopotam · open-meteo", studs=2, fill="#111b30")

flow("M210,81 L296,81", C["ext"], "request", 253, 72)
gate(253, 98, 1)
flow("M480,116 L480,226", C["k9"], "run()", 492, 206, "start")
gate(480, 140, 2)
flow("M630,272 L756,272", C["model"], "every model call", 693, 262)
gate(693, 290, 4)
flow("M910,314 L910,386", C["model"])
flow("M420,314 C420,350 385,350 385,386", C["tool"], "tool call", 372, 352, "end")
gate(398, 336, 5)
flow("M600,386 C600,350 560,350 560,318", C["tool"], "tool result", 612, 352, "start")
gate(585, 340, 6)
flow("M300,423 L254,423", C["ext"])
flow("M600,456 C600,492 145,492 145,460", C["ext"])
flow("M630,250 C700,200 720,120 756,100", C["k9"], "reply → final answer", 744, 136, "start")
gate(705, 178, 7)
gate(560, 216, 3)

svg = ('<svg class="lego" viewBox="0 0 1120 510" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
       'aria-label="Request path: visitor, K9-AIF orchestrator adapter, OpenAI Agents SDK runner, K9 Model Router and local model, '
       'two tools and their public services, answer with receipt; numbered checkpoints on every crossing inside the Shield band">'
       '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
       '<path d="M0,0 L10,5 L0,10 z" fill="#7b8baa"/></marker>'
       '<filter id="gl" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="6" result="b"/>'
       '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
       + "\n".join(out) + "</svg>")
open(__import__("sys").argv[1], "w").write(svg)
