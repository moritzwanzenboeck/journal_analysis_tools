"""Text cleanup and counting shared with the standalone notebook."""

import re
from html import escape
from unicodedata import normalize

LINE_END_HYPHEN = re.compile(r"(?<=\w)[-\u2010\u00ad][ \t]*\n[ \t]*(?=\w)")
# Numbered section/subsection headings are excluded from paragraph counts.
NUMBERED_HEADING = re.compile(r"^[^\S\n]*(?:\d+\.|\d+(?:\.\d+)+\.?)[^\S\n]+[^\W\d_].*$")
WORD = re.compile(r"[^\W_]+(?:['’\-\u2010\u2011][^\W_]+)*", re.UNICODE)


def normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def find_line_end_hyphens(text):
    """Return numbered split occurrences for the review selector."""
    text = normalize_newlines(text)
    splits = []
    for index, match in enumerate(LINE_END_HYPHEN.finditer(text)):
        left = re.search(r"[\w'’\-\u2010\u2011]+$", text[:match.start()])
        right = re.match(r"[\w'’\-\u2010\u2011]+", text[match.end():])
        left, right = left.group(0), right.group(0)
        splits.append({
            "index": index,
            "line": text.count("\n", 0, match.start()) + 1,
            "left": left,
            "right": right,
            "joined": left + right,
            "hyphenated": left + "-" + right,
        })
    return splits



def ends_paragraph(text):
    """Recognize final punctuation or footnote digits without a leading zero."""
    text = text.rstrip()
    # Normalize only for recognition: mathematical italic 𝑝 also means p.
    # A p-value can omit the leading zero, e.g. (𝑝<.1 followed by a wrap.
    if re.search(r"(?<!\w)p\s*(?:[<>=≤≥≈]\s*)+[+-]?(?:\d+)?\.\d+$",
                 normalize("NFKC", text), re.IGNORECASE):
        return False
    # A zero-prefixed suffix is likely a decimal, such as p = 0.001.
    return re.search(r"[.:?!](?:[1-9]\d*)?$", text) is not None


def attach_single_character_lines(text):
    """Attach equation remnants to the preceding body line, never across a heading."""
    output = []
    previous_body = None
    for line in normalize_newlines(text).split("\n"):
        stripped = line.strip()
        if NUMBERED_HEADING.fullmatch(line):
            output.append(line)
            previous_body = None
        elif len(stripped) == 1:
            if previous_body is not None:
                output[previous_body] = output[previous_body].rstrip() + " " + stripped
            else:
                output.append(line)
        else:
            output.append(line)
            if stripped:
                previous_body = len(output) - 1
    return "\n".join(output)


def join_unfinished_lines(text):
    """Join unfinished body lines and ensure blank lines between paragraphs."""
    parts = re.split(r"(\n(?:[^\S\n]*\n)*)", attach_single_character_lines(text))
    for index in range(1, len(parts), 2):
        previous, following = parts[index - 1], parts[index + 1]
        if (previous.strip() and following.strip()
                and not NUMBERED_HEADING.fullmatch(previous)
                and not NUMBERED_HEADING.fullmatch(following)
                and not ends_paragraph(previous)):
            parts[index - 1] = previous.rstrip()
            # Wrapped closing brackets attach directly to the expression.
            parts[index] = "" if following.lstrip().startswith((")", "]", "}")) else " "
            parts[index + 1] = following.lstrip()
        elif previous.strip() and following.strip() and parts[index].count("\n") == 1:
            # Preserve existing blank lines; add one only when it is missing.
            parts[index] = "\n\n"
    return "".join(parts)


def clean_text(text, keep_hyphens=(), unwrap_lines=False):
    """Join split words; retain a genuine hyphen for selected occurrence indexes."""
    text = normalize_newlines(text)
    keep_hyphens = set(keep_hyphens)
    matches = iter(enumerate(LINE_END_HYPHEN.finditer(text)))

    def replacement(match):
        index, _ = next(matches)
        if index not in keep_hyphens:
            return ""
        # A soft hyphen is invisible; replace it with a visible real hyphen.
        return "-" if match.group(0)[0] == "\u00ad" else match.group(0)[0]

    cleaned = join_unfinished_lines(LINE_END_HYPHEN.sub(replacement, text))
    if unwrap_lines:
        cleaned = re.sub(r"[ \t]*\n[ \t]*", "\n", cleaned)
        lines = cleaned.split("\n")
        pieces = []
        for index, line in enumerate(lines):
            pieces.append(line)
            if index + 1 < len(lines):
                following = lines[index + 1]
                join = (line.strip() and following.strip()
                        and not NUMBERED_HEADING.fullmatch(line)
                        and not NUMBERED_HEADING.fullmatch(following))
                pieces.append(" " if join else "\n")
        cleaned = "".join(pieces)
    return cleaned


def count_paragraphs(text, paragraph_mode="lines"):
    lines = join_unfinished_lines(text).split("\n")
    if paragraph_mode == "lines":
        return sum(len(line.strip()) > 1 and ends_paragraph(line)
                   and not NUMBERED_HEADING.fullmatch(line) for line in lines)
    if paragraph_mode != "blank_lines":
        raise ValueError("paragraph_mode must be 'lines' or 'blank_lines'")
    paragraphs = 0
    last_body_line = ""
    for line in lines + [""]:
        if not line.strip() or NUMBERED_HEADING.fullmatch(line):
            paragraphs += int(ends_paragraph(last_body_line))
            last_body_line = ""
        elif len(line.strip()) > 1:
            last_body_line = line
    return paragraphs


def count_text(text, paragraph_mode="lines"):
    return {
        "paragraphs": count_paragraphs(text, paragraph_mode),
        "words": len(WORD.findall(text)),
        "characters_including_whitespace": len(text),
        "characters_excluding_whitespace": sum(not char.isspace() for char in text),
    }
