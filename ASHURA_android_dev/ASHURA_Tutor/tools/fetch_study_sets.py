#!/usr/bin/env python3
"""
Build the bundled offline study-set library.

Source: Wikipedia (https://www.wikipedia.org/), licensed CC BY-SA 4.0.
Each subject gets 20 short Markdown notes built from the article's introductory text.
The app reads the manifest, shows the attribution, and can import any note into the
local library, where ASHURA's deterministic QuizBuilder turns it into a mixed test.

Run from the ASHURA_Tutor project root:
    python tools/fetch_study_sets.py --check
    python tools/fetch_study_sets.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ASHURA-Tutor/0.5 (offline educational study packs; local build)"
OUT_DIR = os.path.join("app", "src", "main", "assets", "study_sets")
RETRIEVED = date.today().isoformat()
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

SUBJECTS = [
    ("maths", "Mathematics", "beginner", [
        "Arithmetic", "Fraction", "Percentage", "Algebra", "Linear equation",
        "Quadratic equation", "Function (mathematics)", "Geometry", "Trigonometry",
        "Probability", "Statistics", "Calculus", "Derivative", "Integral",
        "Matrix (mathematics)", "Euclidean vector", "Set (mathematics)", "Number theory",
        "Prime number", "Logarithm",
    ]),
    ("science", "General Science", "beginner", [
        "Scientific method", "Physics", "Chemistry", "Biology", "Earth science",
        "Astronomy", "Cell (biology)", "Energy", "Matter", "Ecosystem", "Evolution",
        "Genetics", "Photosynthesis", "Solar System", "Water cycle", "Electricity",
        "Magnetism", "Force", "Atom", "Molecule",
    ]),
    ("physics", "Physics", "intermediate", [
        "Classical mechanics", "Newton's laws of motion", "Kinematics", "Work (physics)",
        "Energy", "Conservation of energy", "Momentum", "Gravity", "Electromagnetism",
        "Electric charge", "Electric current", "Voltage", "Ohm's law", "Wave", "Sound",
        "Light", "Optics", "Thermodynamics", "Quantum mechanics", "Special relativity",
    ]),
    ("chemistry", "Chemistry", "intermediate", [
        "Atom", "Molecule", "Chemical bond", "Periodic table", "Chemical element",
        "Chemical reaction", "Stoichiometry", "Acid–base reaction", "pH", "Redox",
        "Chemical equilibrium", "Thermochemistry", "Organic chemistry", "Hydrocarbon",
        "Functional group", "Polymer", "Electrochemistry", "Gas laws", "Solution (chemistry)",
        "Chemical kinetics",
    ]),
    ("python", "Python Programming", "beginner", [
        "Python (programming language)", "Variable (computer science)", "Data type",
        "String (computer science)", "List (abstract data type)", "Control flow",
        "Conditional (computer programming)", "Foreach loop", "Function (computer programming)",
        "Recursion (computer science)", "Object-oriented programming", "Class (computer programming)",
        "Exception handling", "Modular programming", "Input/output", "Regular expression",
        "Library (computing)", "Debugging", "Algorithm", "Big O notation",
    ]),
    ("c", "C Programming", "intermediate", [
        "C (programming language)", "C data types", "Pointer (computer programming)",
        "Array (data structure)", "String (computer science)", "Struct (C programming language)",
        "Function (computer programming)", "Control flow", "C dynamic memory allocation",
        "Stack (abstract data type)", "Heap (data structure)", "C preprocessor", "Header file",
        "Compiler", "Linker (computing)", "Undefined behavior", "Bitwise operation", "Input/output",
        "Recursion (computer science)", "C standard library",
    ]),
    ("rust", "Rust Programming", "intermediate", [
        "Rust (programming language)", "Memory safety", "Type system", "Generic programming",
        "Trait (computer programming)", "Pattern matching", "Concurrency (computer science)",
        "Exception handling", "Rust syntax", "Macro (computer science)", "Iterator",
        "Closure (computer programming)", "Smart pointer", "Resource acquisition is initialization",
        "Immutable object", "Functional programming", "Systems programming", "Compilation",
        "Package manager", "Unit testing",
    ]),
    ("electrical-engineering", "Electrical Engineering", "intermediate", [
        "Electrical engineering", "Electrical network", "Ohm's law", "Kirchhoff's circuit laws",
        "Series and parallel circuits", "Alternating current", "Direct current",
        "Electrical impedance", "Capacitor", "Inductor", "Resistor", "Diode", "Transistor",
        "Transformer", "Electric motor", "Electric generator", "Power factor",
        "Three-phase electric power", "Signal processing", "Control theory",
    ]),
    ("electronics", "Basic Electronics and Devices", "beginner", [
        "Electronics", "Electronic component", "Resistor", "Capacitor", "Inductor", "Diode",
        "Light-emitting diode", "Transistor", "Bipolar junction transistor", "MOSFET",
        "Operational amplifier", "Rectifier", "Power supply", "Printed circuit board",
        "Soldering", "Logic gate", "Integrated circuit", "Voltage regulator", "Oscilloscope",
        "Multimeter",
    ]),
    ("advanced-calculus", "Advanced Calculus", "advanced", [
        "Calculus", "Limit (mathematics)", "Continuous function", "Derivative",
        "Partial derivative", "Gradient", "Divergence", "Curl (mathematics)", "Integral",
        "Multiple integral", "Line integral", "Surface integral", "Vector calculus",
        "Taylor series", "Fourier series", "Differential equation", "Ordinary differential equation",
        "Partial differential equation", "Laplace transform", "Series (mathematics)",
    ]),
]


def api(params: dict, attempts: int = 6) -> dict:
    params = dict(params)
    params["format"] = "json"
    params["formatversion"] = "1"
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in (429, 502, 503) and attempt < attempts - 1:
                time.sleep(3 + attempt * 3)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(4 + attempt * 4)
                continue
            raise
    raise last_error  # type: ignore[misc]


def fetch_intros(titles: list[str]) -> dict[str, dict]:
    """One request per batch of 20 intros; returns requested-title -> page."""
    found: dict[str, dict] = {}
    for start in range(0, len(titles), 20):
        batch = titles[start:start + 20]
        data = api({
            "action": "query", "prop": "extracts", "explaintext": "1", "exintro": "1",
            "redirects": "1", "exlimit": "max", "titles": "|".join(batch),
        })
        query = data.get("query", {})
        pages = query.get("pages", {})
        by_title = {page.get("title", ""): page for page in pages.values()}
        redirects = {item["from"]: item["to"] for item in query.get("redirects", [])}
        for title in batch:
            resolved = redirects.get(title, title)
            page = by_title.get(resolved) or by_title.get(title)
            if page is None:
                page = next((p for t, p in by_title.items() if t.lower() == resolved.lower()), None)
            if page and page.get("extract"):
                found[title] = page
        time.sleep(1.25)
    return found


def search_title(query: str) -> str | None:
    data = api({"action": "query", "list": "search", "srsearch": query, "srlimit": "1"})
    hits = data.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def fetch_long(title: str) -> str:
    """Whole-article extracts are limited to one page per request; used only for short intros."""
    data = api({
        "action": "query", "prop": "extracts", "explaintext": "1", "exchars": "4500",
        "redirects": "1", "titles": title,
    })
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        text = page.get("extract", "")
        if text:
            return text
    return ""


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Stop before Wikipedia's trailing apparatus when a longer extract included it.
    text = re.split(r"\n(?:See also|References|Further reading|External links|Notes)\n", text)[0]
    text = text.strip()
    if len(text) > 5200:
        cut = text.rfind(". ", 0, 5200)
        text = text[: cut + 1 if cut > 3000 else 5200].strip()
    return text


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (slug or "study-set")[:64]


def wiki_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def check() -> int:
    missing = []
    for subject_id, name, _level, topics in SUBJECTS:
        found = fetch_intros(topics)
        for title in topics:
            if title not in found:
                print(f"MISSING {subject_id}: {title}")
                missing.append((subject_id, title))
        print(f"CHECK {subject_id}: {len(found)}/{len(topics)}")
    return 1 if missing else 0


def build() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest_subjects = []
    total = 0
    for subject_id, name, level, topics in SUBJECTS:
        found = fetch_intros(topics)
        subject_dir = os.path.join(OUT_DIR, subject_id)
        os.makedirs(subject_dir, exist_ok=True)
        sets = []
        used_slugs = set()
        for index, requested in enumerate(topics, start=1):
            page = found.get(requested)
            if page is None:
                alternate = search_title(requested)
                if alternate:
                    page = fetch_intros([alternate]).get(alternate)
                    if page:
                        print(f"FALLBACK {subject_id}: {requested} -> {alternate}")
            if page is None:
                print(f"SKIP {subject_id}: {requested} (not found)")
                continue
            title = page.get("title", requested)
            text = clean(page.get("extract", ""))
            if len(text) < 500:
                longer = clean(fetch_long(title))
                if len(longer) > len(text):
                    text = longer
            if len(text) < 300:
                print(f"SKIP {subject_id}: {title} (too little text)")
                continue
            base_slug = f"{index:02d}-{slugify(title)}"
            slug = base_slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            used_slugs.add(slug)

            url = wiki_url(title)
            body = f"# {title}\n\n{text}\n"
            path = os.path.join(subject_dir, slug + ".md")
            encoded = body.encode("utf-8")
            with open(path, "wb") as handle:
                handle.write(encoded)
            digest = hashlib.sha256(encoded).hexdigest()
            sets.append({
                "id": f"{subject_id}.{slug}",
                "slug": slug,
                "title": title,
                "file": f"{subject_id}/{slug}.md",
                "sha256": digest,
                "chars": len(body),
                "source": url,
                "license": LICENSE,
                "licenseUrl": LICENSE_URL,
                "retrieved": RETRIEVED,
            })
            total += 1
            print(f"OK {subject_id} {index:02d} {title} ({len(body)} chars)")
        manifest_subjects.append({
            "id": subject_id,
            "name": name,
            "level": level,
            "sets": sets,
        })
        print(f"SUBJECT {subject_id}: {len(sets)} sets")

    manifest = {
        "format": "ashura-study-packs",
        "version": 1,
        "generatedAt": RETRIEVED,
        "source": "Wikipedia",
        "sourceUrl": "https://www.wikipedia.org/",
        "license": LICENSE,
        "licenseUrl": LICENSE_URL,
        "notice": "Each note is a condensed excerpt of the cited Wikipedia article. "
                  "Content is licensed CC BY-SA 4.0 and is stored on-device; no network is used at runtime.",
        "subjects": manifest_subjects,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"TOTAL {total} study sets")
    return 0


def main() -> int:
    if "--check" in sys.argv:
        return check()
    return build()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as error:
        print(f"Network error: {error}", file=sys.stderr)
        raise SystemExit(2)
