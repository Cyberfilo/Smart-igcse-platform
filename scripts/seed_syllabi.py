"""Seed Syllabus / Paper / Topic / Note rows. Idempotent — safe to re-run.

Run via:
    railway run python -m scripts.seed_syllabi

Or locally after migrations:
    FLASK_ENV=development python -m scripts.seed_syllabi

Topic metadata (name, short_name, color, area) lives in this file.
Topic content HTML lives on disk under content/notes/<syllabus_code>/<NN>_<slug>.html
and is upserted into the Note table keyed by topic number.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import Note, Paper, Syllabus, Topic  # noqa: E402

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "notes"


SYLLABI = [
    {"code": "0580", "name": "Cambridge IGCSE Mathematics"},
    {"code": "0654", "name": "Cambridge IGCSE Coordinated Sciences"},
]

PAPERS = [
    {"syllabus_code": "0580", "number": 2, "supports_digital_input": False},
    {"syllabus_code": "0580", "number": 4, "supports_digital_input": False},
    {"syllabus_code": "0654", "number": 2, "supports_digital_input": True},
    {"syllabus_code": "0654", "number": 4, "supports_digital_input": False},
    {"syllabus_code": "0654", "number": 6, "supports_digital_input": False},
]


# ── 0580 Mathematics — 60 topics across 9 areas ──
# Format: (number, name, short_name, color, area_code, area_name, syllabus_ref, description)

TOPICS_0580 = [
    # --- C1 Number ---
    ( 1, "Types of number",              "Number types", "color-purple", "C1", "Number", "C1.1 / E1.1", "Natural, integer, prime, rational, irrational."),
    ( 2, "Sets",                         "Sets",         "color-purple", "C1", "Number", "C1.2 / E1.2", "Set notation, Venn diagrams, union, intersection."),
    ( 3, "Powers, roots, surds",         "Surds",        "color-purple", "C1", "Number", "C1.3 / E1.3", "Perfect squares/cubes, surd manipulation, rationalising."),
    ( 4, "Fractions, decimals, %",       "Frac/dec/%",   "color-purple", "C1", "Number", "C1.4 / E1.4", "Conversions, recurring decimals, equivalence."),
    ( 5, "Ordering",                     "Ordering",     "color-purple", "C1", "Number", "C1.5 / E1.5", "Symbols <, >, ≤, ≥; number-line ordering."),
    ( 6, "Four operations",              "Operations",   "color-purple", "C1", "Number", "C1.6 / E1.6", "BIDMAS / order of operations."),
    ( 7, "Indices I & II",               "Indices",      "color-purple", "C1", "Number", "C1.7, C2.4 / E1.7, E2.4", "Rules of indices, negative, fractional."),
    ( 8, "Standard form",                "Std form",     "color-purple", "C1", "Number", "C1.8 / E1.8", "A × 10ⁿ with 1 ≤ A < 10."),
    ( 9, "Estimation",                   "Estimation",   "color-purple", "C1", "Number", "C1.9 / E1.9", "Rounding and reasonable answers."),
    (10, "Limits of accuracy",           "Bounds",       "color-purple", "C1", "Number", "C1.10 / E1.10", "Upper and lower bounds in calculations."),
    (11, "Ratio & proportion",           "Ratio",        "color-purple", "C1", "Number", "C1.11 / E1.11", "Sharing, direct and inverse proportion."),
    (12, "Rates",                        "Rates",        "color-purple", "C1", "Number", "C1.12 / E1.12", "Speed, density, pressure, average rates."),
    (13, "Percentages & compound interest", "% & C.I.",  "color-purple", "C1", "Number", "C1.13 / E1.13", "Percentage change, compound interest, reverse %."),
    (14, "Calculator, time, money",      "Tools",        "color-purple", "C1", "Number", "C1.14-1.16 / E1.14-1.16", "Calculator use, 24-hour clock, currency conversion."),
    (15, "Exponential growth & decay",   "Growth/decay", "color-purple", "C1", "Number", "E1.18", "Continuous growth/decay (Extended)."),
    # --- C2 Algebra and graphs ---
    (16, "Introduction to algebra",      "Algebra intro","color-teal",   "C2", "Algebra", "C2.1 / E2.1", "Substitution, expressions, notation."),
    (17, "Algebraic manipulation",       "Algebra",      "color-teal",   "C2", "Algebra", "C2.2, E2.3", "Expand, factorise, simplify algebraic fractions."),
    (18, "Linear equations & simultaneous", "Linear eqs","color-teal",   "C2", "Algebra", "C2.5 / E2.5", "Solving linear + simultaneous linear equations."),
    (19, "Quadratic equations",          "Quadratics",   "color-teal",   "C2", "Algebra", "E2.5", "Factorising, formula, completing the square."),
    (20, "Inequalities",                 "Inequalities", "color-teal",   "C2", "Algebra", "C2.6 / E2.6", "Solving, graphical regions."),
    (21, "Sequences",                    "Sequences",    "color-teal",   "C2", "Algebra", "C2.7 / E2.7", "Linear, quadratic, geometric; nth term."),
    (22, "Direct & inverse proportion",  "Proportion",   "color-teal",   "C2", "Algebra", "E2.8", "y = kx, y = k/x, y = kx², y = k√x."),
    (23, "Motion graphs",                "Motion graphs","color-teal",   "C2", "Algebra", "C2.9 / E2.9", "Distance-time, speed-time, gradient and area."),
    (24, "Graphs of functions",          "Graphs",       "color-teal",   "C2", "Algebra", "C2.10 / E2.10", "Linear, quadratic, cubic, reciprocal, exponential."),
    (25, "Sketching curves",             "Curves",       "color-teal",   "C2", "Algebra", "C2.11 / E2.11", "Key features: roots, turning points, asymptotes."),
    (26, "Transformations of graphs",    "Graph trans.", "color-teal",   "C2", "Algebra", "E2.12", "f(x+a), f(x)+a, kf(x), f(kx)."),
    (27, "Functions",                    "Functions",    "color-teal",   "C2", "Algebra", "E2.13", "Composite fg(x), inverse f⁻¹(x)."),
    (28, "Differentiation",              "Differentiation","color-teal", "C2", "Algebra", "E2.13", "Power rule, tangents, normals, stationary points."),
    # --- C3 Coordinate geometry ---
    (29, "Coordinates & linear graphs",  "Coords",       "color-coral",  "C3", "Coord. geometry", "C3.1, C3.2 / E3.1, E3.2", "Plotting, drawing linear graphs."),
    (30, "Gradient & equation of line",  "Gradient",     "color-coral",  "C3", "Coord. geometry", "C3.3, C3.5 / E3.3, E3.5", "y = mx + c, finding equations."),
    (31, "Length & midpoint",            "Length/mid",   "color-coral",  "C3", "Coord. geometry", "E3.4", "Distance and midpoint formulas (Extended)."),
    (32, "Parallel & perpendicular",     "Par / perp",   "color-coral",  "C3", "Coord. geometry", "C3.6 / E3.7", "m₁ = m₂ (par), m₁m₂ = −1 (perp)."),
    # --- C4 Geometry ---
    (33, "Geometrical terms",            "Geo terms",    "color-pink",   "C4", "Geometry", "C4.1 / E4.1", "Polygons, quadrilaterals, solids, vocabulary."),
    (34, "Geometrical constructions",    "Constructs",   "color-pink",   "C4", "Geometry", "C4.2 / E4.2", "Ruler-and-compass: bisectors, perpendicular."),
    (35, "Scale drawings",               "Scale",        "color-pink",   "C4", "Geometry", "C4.3 / E4.3", "Linear scales, bearings on a map."),
    (36, "Similarity",                   "Similarity",   "color-pink",   "C4", "Geometry", "C4.4 / E4.4", "Ratios of sides, area (k²), volume (k³)."),
    (37, "Symmetry",                     "Symmetry",     "color-pink",   "C4", "Geometry", "C4.5 / E4.5", "Line and rotational symmetry; 3D symmetry planes."),
    (38, "Angles",                       "Angles",       "color-pink",   "C4", "Geometry", "C4.6 / E4.6", "Parallel lines, interior/exterior, polygon sums."),
    (39, "Circle theorems",              "Circle thms",  "color-pink",   "C4", "Geometry", "C4.7, E4.8", "Angles in circles, tangents, alternate segment."),
    # --- C5 Mensuration ---
    (40, "Units of measure",             "Units",        "color-blue",   "C5", "Mensuration", "C5.1 / E5.1", "Length, area, volume, mass, capacity conversions."),
    (41, "Area & perimeter",             "Area",         "color-blue",   "C5", "Mensuration", "C5.2 / E5.2", "Rectangles, triangles, parallelograms, trapezia."),
    (42, "Circles, arcs, sectors",       "Circles",      "color-blue",   "C5", "Mensuration", "C5.3 / E5.3", "Circumference, area, arc length, sector area."),
    (43, "Surface area & volume",        "SA & Vol",     "color-blue",   "C5", "Mensuration", "C5.4 / E5.4", "Prisms, cylinders, cones, spheres, pyramids."),
    (44, "Compound shapes",              "Compound",     "color-blue",   "C5", "Mensuration", "C5.5 / E5.5", "Composite 2D and 3D figures; missing dimensions."),
    # --- C6 Trigonometry ---
    (45, "Pythagoras' theorem",          "Pythagoras",   "color-amber",  "C6", "Trigonometry", "C6.1 / E6.1", "a² + b² = c² in right triangles."),
    (46, "Right-angled trigonometry",    "Right trig",   "color-amber",  "C6", "Trigonometry", "C6.2 / E6.2", "SOH CAH TOA; finding sides and angles."),
    (47, "Exact values & trig 3D",       "Exact trig",   "color-amber",  "C6", "Trigonometry", "E6.3", "Exact sin/cos/tan of 30°, 45°, 60°; 3D problems."),
    (48, "Sine & cosine rules",          "Sine/cos rule","color-amber",  "C6", "Trigonometry", "E6.4, E6.5", "a/sinA = b/sinB, a² = b² + c² − 2bc·cosA, ½ab sinC."),
    (49, "Bearings",                     "Bearings",     "color-amber",  "C6", "Trigonometry", "E6.6", "Three-figure bearings from North, clockwise."),
    # --- C7 Transformations & vectors ---
    (50, "Transformations",              "Transforms",   "color-purple-alt", "C7", "Trans. & vectors", "C7.1 / E7.1", "Reflection, rotation, translation, enlargement."),
    (51, "Combined transformations",     "Combined",     "color-purple-alt", "C7", "Trans. & vectors", "E7.2, E7.3", "Composing transformations; invariant points."),
    (52, "Vectors",                      "Vectors",      "color-purple-alt", "C7", "Trans. & vectors", "C7.4 / E7.4", "Column form, magnitude, AB = b − a, midpoint."),
    # --- C8 Probability ---
    (53, "Introduction to probability",  "Probability",  "color-pink",   "C8", "Probability", "C8.1 / E8.1", "P(A), sample space, basic definitions."),
    (54, "Relative & expected frequency","Exp freq",     "color-pink",   "C8", "Probability", "C8.2 / E8.2", "From experimental data; expected occurrences."),
    (55, "Combined events",              "Combined ev",  "color-pink",   "C8", "Probability", "C8.3 / E8.3", "Independent × , exclusive +, tree diagrams."),
    (56, "Conditional probability",      "Conditional",  "color-pink",   "C8", "Probability", "E8.4", "P(B | A); without-replacement problems."),
    # --- C9 Statistics ---
    (57, "Classifying data",             "Data types",   "color-blue",   "C9", "Statistics", "C9.1 / E9.1", "Discrete, continuous, qualitative, quantitative."),
    (58, "Interpreting data",            "Interpret",    "color-blue",   "C9", "Statistics", "C9.2 / E9.2", "Reading tables and charts; drawing conclusions."),
    (59, "Averages & range",             "Averages",     "color-blue",   "C9", "Statistics", "C9.3 / E9.3", "Mean, median, mode, range; grouped data."),
    (60, "Statistical charts",           "Charts",       "color-blue",   "C9", "Statistics", "C9.4 / E9.4", "Bar, pie, pictograms, frequency polygons."),
    (61, "Scatter diagrams",             "Scatter",      "color-blue",   "C9", "Statistics", "C9.5 / E9.5", "Correlation, line of best fit."),
    (62, "Cumulative frequency",         "Cum. freq",    "color-blue",   "C9", "Statistics", "E9.6", "Median, quartiles, IQR from curve (Extended)."),
    (63, "Histograms",                   "Histograms",   "color-blue",   "C9", "Statistics", "E9.7", "Frequency density for unequal class widths."),
]


# ── 0654 Coordinated Sciences — populated in a later batch ──
TOPICS_0654: list[tuple] = []


def _content_files(code: str) -> dict[int, str]:
    """Return {topic_number: content_html} for all *.html under content/notes/<code>/."""
    dir_ = CONTENT_DIR / code
    if not dir_.exists():
        return {}
    out: dict[int, str] = {}
    for path in sorted(dir_.glob("*.html")):
        m = re.match(r"(\d+)_[a-z0-9-]+\.html$", path.name)
        if not m:
            continue
        num = int(m.group(1))
        out[num] = path.read_text(encoding="utf-8")
    return out


def _upsert_syllabus(code: str, name: str) -> Syllabus:
    row = Syllabus.query.filter_by(code=code).first()
    if row is None:
        row = Syllabus(code=code, name=name)
        db.session.add(row)
        db.session.flush()
    else:
        row.name = name
    return row


def _upsert_paper(syllabus_id: int, number: int, supports_digital: bool) -> Paper:
    row = Paper.query.filter_by(syllabus_id=syllabus_id, number=number).first()
    if row is None:
        row = Paper(syllabus_id=syllabus_id, number=number, supports_digital_input=supports_digital)
        db.session.add(row)
        db.session.flush()
    else:
        row.supports_digital_input = supports_digital
    return row


def _upsert_topic(syllabus_id: int, row_tuple: tuple) -> Topic:
    num, name, short, color, area_code, area_name, ref, desc = row_tuple
    row = Topic.query.filter_by(syllabus_id=syllabus_id, number=num).first()
    if row is None:
        row = Topic(syllabus_id=syllabus_id, number=num)
        db.session.add(row)
    row.name = name
    row.short_name = short
    row.color_class = color
    row.area_code = area_code
    row.area_name = area_name
    row.syllabus_ref = ref
    row.description = desc
    db.session.flush()
    return row


def _upsert_note(topic_id: int, content_html: str) -> Note:
    row = Note.query.filter_by(topic_id=topic_id).first()
    if row is None:
        row = Note(topic_id=topic_id, content_html=content_html, display_order=0)
        db.session.add(row)
    else:
        row.content_html = content_html
    return row


def _seed_syllabus_topics(syllabus_code: str, topic_rows: list[tuple]) -> tuple[int, int]:
    """Upserts topics for one syllabus and attaches note HTML from disk.
    Returns (topics_seeded, notes_seeded)."""
    syllabus = Syllabus.query.filter_by(code=syllabus_code).first()
    if syllabus is None:
        return (0, 0)

    files = _content_files(syllabus_code)

    topics_done = 0
    notes_done = 0
    for row_tuple in topic_rows:
        t = _upsert_topic(syllabus.id, row_tuple)
        topics_done += 1
        body = files.get(row_tuple[0])
        if body:
            _upsert_note(t.id, body)
            notes_done += 1

    return (topics_done, notes_done)


def run() -> None:
    app = create_app()
    with app.app_context():
        for s in SYLLABI:
            _upsert_syllabus(s["code"], s["name"])
        db.session.flush()

        for p in PAPERS:
            syll = Syllabus.query.filter_by(code=p["syllabus_code"]).first()
            _upsert_paper(syll.id, p["number"], p["supports_digital_input"])

        t0580, n0580 = _seed_syllabus_topics("0580", TOPICS_0580)
        t0654, n0654 = _seed_syllabus_topics("0654", TOPICS_0654)

        db.session.commit()
        print(
            f"Seeded 0580: {t0580} topics, {n0580} notes from content/notes/0580/\n"
            f"Seeded 0654: {t0654} topics, {n0654} notes from content/notes/0654/\n"
            f"Totals: {Syllabus.query.count()} syllabi, {Paper.query.count()} papers, "
            f"{Topic.query.count()} topics, {Note.query.count()} notes."
        )


if __name__ == "__main__":
    run()
