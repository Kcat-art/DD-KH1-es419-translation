from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PO_ROOT = ROOT / "po"
OUT_DIR = ROOT / "assets" / "progress"

HIDDEN_LINES_PATH = (
    ROOT / "assets" / "companion" / "hidden_lines.json"
)

TEXTURE_PROGRESS_PATH = (
    ROOT / "texturas" / "progreso.json"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


LINE_STATUS_RE = re.compile(
    r'^#\.\s+(?:'
    r'lineStatus\s*:\s*|'
    r'line_status\s*=\s*|'
    r'y4:line_status\s*=\s*'
    r')(.+)$',
    re.MULTILINE | re.IGNORECASE,
)

FILE_STATUS_RE = re.compile(
    r'^#\.\s+(?:'
    r'fileStatus\s*:\s*|'
    r'file_status\s*=\s*|'
    r'y4:file_status\s*=\s*'
    r')(.+)$',
    re.MULTILINE | re.IGNORECASE,
)

REVIEWED_BY_RE = re.compile(
    r'^#\.\s+y4:reviewed_by\s*=\s*(.+)$',
    re.MULTILINE | re.IGNORECASE,
)

FIELD_START_RE = re.compile(
    r'^(msgctxt|msgid|msgstr(?:\[\d+\])?)\s+(.+)$'
)


def format_pct(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def badge_color(pct: float) -> str:
    if pct >= 99.99:
        return "brightgreen"

    if pct >= 75:
        return "green"

    if pct >= 50:
        return "yellow"

    if pct >= 25:
        return "orange"

    return "red"


def normalize_status(value: str) -> str:
    return (
        value
        .strip()
        .strip('"')
        .lower()
    )


def po_unquote(value: str) -> str:
    value = value.strip()

    if not value.startswith('"'):
        return ""

    try:
        return ast.literal_eval(value)

    except Exception:
        return value.strip('"')


def extract_po_field(
    block: str,
    field_name: str,
) -> str:

    output: list[str] = []
    collecting = False

    for line in block.splitlines():
        match = FIELD_START_RE.match(line)

        if match:
            current_field = match.group(1)

            if current_field.startswith("msgstr"):
                current_field = "msgstr"

            collecting = (
                current_field == field_name
            )

            if collecting:
                output.append(
                    po_unquote(match.group(2))
                )

            continue

        if (
            collecting
            and line.strip().startswith('"')
        ):
            output.append(
                po_unquote(line.strip())
            )
            continue

        if collecting and (
            line.startswith("#")
            or not line.strip()
        ):
            continue

        if collecting:
            break

    return "".join(output)


def iter_entries(text: str):
    for block in re.split(
        r"\n\s*\n",
        text,
    ):
        if not block.strip():
            continue

        # Cabecera PO
        if (
            'msgid ""' in block
            and "Project-Id-Version" in block
        ):
            continue

        if (
            "msgid " not in block
            or "msgstr" not in block
        ):
            continue

        yield block


def load_hidden_terms() -> list[str]:
    """
    Compatibilidad con hidden_lines.json del Companion.

    Si Kurohyou no tiene ese archivo, simplemente
    no se excluye ninguna línea.
    """

    if not HIDDEN_LINES_PATH.exists():
        return []

    try:
        data = json.loads(
            HIDDEN_LINES_PATH.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return []

    terms = data.get(
        "blocked_terms",
        [],
    )

    if not isinstance(terms, list):
        return []

    return sorted({
        str(term).strip().lower()
        for term in terms
        if str(term).strip()
    })


def parse_po(
    path: Path,
    hidden_terms: list[str],
):
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    total = 0
    translated = 0
    reviewed = 0
    hidden = 0

    file_reviewed = any(
        normalize_status(status) == "reviewed"
        for status
        in FILE_STATUS_RE.findall(text)
    )

    for block in iter_entries(text):

        haystack = "\n".join([
            extract_po_field(
                block,
                "msgctxt",
            ),
            extract_po_field(
                block,
                "msgid",
            ),
            extract_po_field(
                block,
                "msgstr",
            ),
        ]).lower()

        if any(
            term in haystack
            for term in hidden_terms
        ):
            hidden += 1
            continue

        total += 1

        msgstr = extract_po_field(
            block,
            "msgstr",
        )

        if msgstr.strip():
            translated += 1

        statuses = (
            LINE_STATUS_RE.findall(block)
        )

        line_reviewed = (
            bool(statuses)
            and normalize_status(
                statuses[-1]
            ) == "reviewed"
        )

        reviewed_by = (
            REVIEWED_BY_RE.search(block)
            is not None
        )

        if (
            line_reviewed
            or reviewed_by
            or file_reviewed
        ):
            reviewed += 1

    return (
        total,
        translated,
        reviewed,
        hidden,
    )


def classify_area(
    repo_relative: str,
) -> str | None:

    path = (
        repo_relative
        .replace("\\", "/")
        .lower()
    )

    if path.startswith(
        "po/scaleform/"
    ):
        return "Cinemáticas"

    if path.startswith(
        "po/kurohyou/city/"
    ):
        return "Historia / Ciudad"

    if path.startswith(
        "po/kurohyou/cabaclu/"
    ):
        return "Cabaret"

    if path.startswith(
        "po/kurohyou/globals/"
    ):
        return "Globales"

    if path.startswith(
        "po/kurohyou/"
    ):
        return "Otros Kurohyou"

    return None


def collect_texture_progress() -> dict:
    """
    Kurohyou ya mantiene su propio
    texturas/progreso.json.

    Por eso no necesitamos contar
    los originales físicamente.
    """

    if not TEXTURE_PROGRESS_PATH.exists():
        return {
            "total": 0,
            "translated": 0,
            "reviewed": 0,
            "no_translation_needed": 0,
            "completed": 0,
            "pending": 0,
            "pct": 0.0,
            "pct_reviewed": 0.0,
        }

    try:
        data = json.loads(
            TEXTURE_PROGRESS_PATH.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        print(
            "No se pudo leer "
            "texturas/progreso.json:",
            exc,
        )

        return {
            "total": 0,
            "translated": 0,
            "reviewed": 0,
            "no_translation_needed": 0,
            "completed": 0,
            "pending": 0,
            "pct": 0.0,
            "pct_reviewed": 0.0,
        }

    total = int(
        data.get(
            "total",
            data.get(
                "physical_total",
                0,
            ),
        )
        or 0
    )

    translated = int(
        data.get(
            "translated",
            0,
        )
        or 0
    )

    reviewed = int(
        data.get(
            "reviewed",
            0,
        )
        or 0
    )

    no_translation_needed = int(
        data.get(
            "no_translation_needed",
            0,
        )
        or 0
    )

    completed = int(
        data.get(
            "completed",
            translated
            + no_translation_needed,
        )
        or 0
    )

    pending = int(
        data.get(
            "pending",
            max(
                0,
                total - completed,
            ),
        )
        or 0
    )

    pct = (
        completed
        * 100.0
        / total

        if total
        else 0.0
    )

    pct_reviewed = (
        reviewed
        * 100.0
        / total

        if total
        else 0.0
    )

    return {
        "total": total,
        "translated": translated,
        "reviewed": reviewed,
        "no_translation_needed": (
            no_translation_needed
        ),
        "completed": completed,
        "pending": pending,
        "pct": round(
            pct,
            2,
        ),
        "pct_reviewed": round(
            pct_reviewed,
            2,
        ),
    }


def global_pct(
    translated: int,
    reviewed: int,
    entries_total: int,
    textures_completed: int,
    textures_total: int,
) -> float:

    total_units = (
        (2 * entries_total)
        + textures_total
    )

    if total_units <= 0:
        return 0.0

    completed_units = (
        translated
        + reviewed
        + textures_completed
    )

    return (
        completed_units
        * 100.0
        / total_units
    )


def make_badge(
    label: str,
    pct: float,
) -> dict:

    return {
        "schemaVersion": 1,
        "label": label,
        "message": (
            f"{format_pct(pct)}%"
        ),
        "color": badge_color(pct),
        "cacheSeconds": 300,
    }


AREA_ORDER = [
    "Historia / Ciudad",
    "Cinemáticas",
    "Globales",
    "Cabaret",
    "Otros Kurohyou",
]


def build_readme(
    summary: dict,
    areas: dict,
) -> str:

    lines = [
        "## Progreso del proyecto",
        "",
        (
            f"**Traducción global:** "
            f"{summary['entries_translated']}/"
            f"{summary['entries_total']} "
            f"({format_pct(summary['pct_translated'])}%)"
        ),
        (
            f"**Revisión global:** "
            f"{summary['entries_reviewed']}/"
            f"{summary['entries_total']} "
            f"({format_pct(summary['pct_reviewed'])}%)"
        ),
        (
            f"**Texturas:** "
            f"{summary['textures_completed']}/"
            f"{summary['textures_total']} "
            f"({format_pct(summary['pct_textures'])}%)"
        ),
        (
            f"**Progreso global:** "
            f"{format_pct(summary['pct_global'])}%"
        ),
        "",
        "| Área | Traducción | Revisión |",
        "|---|---:|---:|",
    ]

    for name in AREA_ORDER:

        if name not in areas:
            continue

        data = areas[name]

        lines.append(
            f"| {name} | "
            f"{data['translated']}/"
            f"{data['total']} "
            f"({format_pct(data['pct_translated'])}%) | "
            f"{data['reviewed']}/"
            f"{data['total']} "
            f"({format_pct(data['pct_reviewed'])}%) |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    hidden_terms = (
        load_hidden_terms()
    )

    if not PO_ROOT.exists():
        raise SystemExit(
            "No existe la carpeta po/"
        )

    po_files = sorted(
        path
        for path
        in PO_ROOT.rglob("*.po")
        if path.is_file()
        and not any(
            part.lower()
            in {
                ".git",
                "cache",
                "backups",
            }
            for part in path.parts
        )
    )

    files_total = 0
    files_translated = 0
    files_reviewed = 0

    entries_total = 0
    entries_translated = 0
    entries_reviewed = 0
    entries_hidden = 0

    areas = defaultdict(
        lambda: {
            "files_total": 0,
            "files_translated": 0,
            "files_reviewed": 0,

            "total": 0,
            "translated": 0,
            "reviewed": 0,
            "hidden": 0,
        }
    )

    for po in po_files:

        (
            total,
            translated,
            reviewed,
            hidden,
        ) = parse_po(
            po,
            hidden_terms,
        )

        repo_relative = (
            po.relative_to(ROOT)
            .as_posix()
        )

        files_total += 1

        entries_total += total
        entries_translated += translated
        entries_reviewed += reviewed
        entries_hidden += hidden

        if (
            total > 0
            and reviewed == total
        ):
            files_reviewed += 1

        elif (
            total > 0
            and translated == total
        ):
            files_translated += 1

        area = classify_area(
            repo_relative
        )

        if area is None:
            continue

        area_data = areas[area]

        area_data[
            "files_total"
        ] += 1

        area_data[
            "total"
        ] += total

        area_data[
            "translated"
        ] += translated

        area_data[
            "reviewed"
        ] += reviewed

        area_data[
            "hidden"
        ] += hidden

        if (
            total > 0
            and reviewed == total
        ):
            area_data[
                "files_reviewed"
            ] += 1

        elif (
            total > 0
            and translated == total
        ):
            area_data[
                "files_translated"
            ] += 1

    textures = (
        collect_texture_progress()
    )

    pct_translated = (
        entries_translated
        * 100.0
        / entries_total

        if entries_total
        else 0.0
    )

    pct_reviewed = (
        entries_reviewed
        * 100.0
        / entries_total

        if entries_total
        else 0.0
    )

    areas_out = {}

    for name, data in areas.items():

        total = data["total"]

        areas_out[name] = {
            **data,

            "pct_translated": (
                round(
                    data["translated"]
                    * 100.0
                    / total,
                    2,
                )
                if total
                else 0.0
            ),

            "pct_reviewed": (
                round(
                    data["reviewed"]
                    * 100.0
                    / total,
                    2,
                )
                if total
                else 0.0
            ),
        }

    summary = {
        "files_total": (
            files_total
        ),
        "files_translated": (
            files_translated
        ),
        "files_reviewed": (
            files_reviewed
        ),

        "entries_total": (
            entries_total
        ),
        "entries_translated": (
            entries_translated
        ),
        "entries_reviewed": (
            entries_reviewed
        ),
        "entries_hidden": (
            entries_hidden
        ),

        "hidden_terms_count": (
            len(hidden_terms)
        ),

        "pct_translated": round(
            pct_translated,
            2,
        ),

        "pct_reviewed": round(
            pct_reviewed,
            2,
        ),

        "textures_total": (
            textures["total"]
        ),
        "textures_translated": (
            textures["translated"]
        ),
        "textures_reviewed": (
            textures["reviewed"]
        ),
        "textures_no_translation_needed": (
            textures[
                "no_translation_needed"
            ]
        ),
        "textures_completed": (
            textures["completed"]
        ),
        "textures_pending": (
            textures["pending"]
        ),

        "pct_textures": (
            textures["pct"]
        ),

        "pct_textures_reviewed": (
            textures[
                "pct_reviewed"
            ]
        ),

        "pct_global": round(
            global_pct(
                entries_translated,
                entries_reviewed,
                entries_total,
                textures["completed"],
                textures["total"],
            ),
            2,
        ),

        "areas": areas_out,
    }

    (
        OUT_DIR / "summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    badges = (
        (
            "translation_badge.json",
            "traducción",
            summary[
                "pct_translated"
            ],
        ),
        (
            "review_badge.json",
            "revisión",
            summary[
                "pct_reviewed"
            ],
        ),
        (
            "texture_badge.json",
            "texturas",
            summary[
                "pct_textures"
            ],
        ),
        (
            "global_badge.json",
            "progreso global",
            summary[
                "pct_global"
            ],
        ),
    )

    for (
        filename,
        label,
        pct,
    ) in badges:

        (
            OUT_DIR / filename
        ).write_text(
            json.dumps(
                make_badge(
                    label,
                    pct,
                ),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    (
        OUT_DIR
        / "readme_progress.md"
    ).write_text(
        build_readme(
            summary,
            areas_out,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
