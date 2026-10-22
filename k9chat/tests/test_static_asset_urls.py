# SPDX-License-Identifier: Apache-2.0
"""Every template must reference /static files through asset(...), which
adds a content-hash ?v= (app.py). A bare "/static/x.js" lets browsers keep
a stale copy after a deploy -- it once left the Job Queue panel stuck on
"Loading...". Test: no template contains a literal src/href="/static/...".
"""
import pathlib
import re

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "templates"


def test_templates_use_hashed_asset_urls():
    offenders = []
    for tpl in sorted(TEMPLATES.glob("*.html")):
        for n, line in enumerate(tpl.read_text().splitlines(), 1):
            if re.search(r'(?:src|href)\s*=\s*["\']/static/', line):
                offenders.append(f"{tpl.name}:{n}: {line.strip()}")
    assert not offenders, "use {{ asset('...') }} for static files:\n" + "\n".join(offenders)
