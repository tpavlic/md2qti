#!/usr/bin/env python3
"""
md2t2qti.py — Convert a Markdown-only quiz spec into text2qti plaintext.

Authoring schema (summary):
- H1 (#) = Quiz title; description = all content until first H2.
- Each question starts with H2: "## <short title> [(points: N)] {type=TYPE[, key=val,...]}"
  - TYPE in {mc, ma, num, fill, essay, file, text}
  - Optional attrs: number, points
  - Either (points: N) or {..., points=N[, ...]}; if both, {points} wins. If omitted (and type!=text), default 1.
- Prompt = content from after H2 until the first "answers cue" for that type:
  - mc/ma: first task list " - [ ] " or " - [x] "
  - num: line "### Answer:" then next line starting with "="
  - fill: line "### Answers:" then bullets "- ..."
  - essay/file/text: prompt only
- Feedback:
  - Per-choice (mc/ma): indented blockquotes under a choice belong to that choice.
  - Question-level (mc/ma/num/fill): top-level blockquotes AFTER answers. Prefixes (case-insensitive):
      "Correct:", "Incorrect:", "General:"; no prefix => General.
  - Essay/file/text: ignore feedback if present.
- Emission to text2qti follows the mapping in the design spec.

Usage:
    python md2t2qti.py input.md [-o output.txt]

Writes text2qti plaintext to stdout unless -o is specified.
"""

import argparse
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

# ------------------------------ Data models ------------------------------

@dataclass
class FeedbackBlock:
    kind: str  # 'general', 'correct', 'incorrect'
    lines: List[str]

@dataclass
class Choice:
    text_lines: List[str]         # markdown lines for the choice text
    correct: bool
    feedback_lines: List[str] = field(default_factory=list)  # per-choice

@dataclass
class Item:
    kind: str  # mc, ma, num, fill, essay, file, text
    title: str
    points: Optional[float]
    attrs: Dict[str, str]
    prompt_lines: List[str]

    # mc/ma
    choices: List[Choice] = field(default_factory=list)

    # num
    numeric_spec: Optional[str] = None

    # fill
    fill_answers: List[str] = field(default_factory=list)

    # question-level feedback (mc, ma, num, fill)
    q_feedback: List[FeedbackBlock] = field(default_factory=list)

    # original Markdown header number (e.g., "12."), if present
    qnum: Optional[int] = None

    # comments that appear after the question content in Markdown (emit top-level after question)
    trailing_comments: List[str] = field(default_factory=list)

@dataclass
class Quiz:
    title: str
    description_lines: List[str]
    items: List[Item]
    feedback_is_solution: Optional[bool] = None
    solutions_sample_groups: Optional[bool] = None
    solutions_randomize_groups: Optional[bool] = None
    shuffle_answers: Optional[bool] = None
    show_correct_answers: Optional[bool] = None
    one_question_at_a_time: Optional[bool] = None
    cant_go_back: Optional[bool] = None
# ------------------------------ Helpers ------------------------------

OPT_LINE_RE = re.compile(r'^(?:\s*>\s*)?\s*(feedback is solution|solutions sample groups|solutions randomize groups|shuffle answers|show correct answers|one question at a time|can\'?t go back)\s*:\s*(true|false)\s*$', re.IGNORECASE)
OPT_HTML_RE = re.compile(r'^\s*<!\-\-#\s*(feedback is solution|solutions sample groups|solutions randomize groups|shuffle answers|show correct answers|one question at a time|can\'?t go back)\s*:\s*(true|false)\s*\-\->\s*$', re.IGNORECASE)
def parse_options_from_desc(desc_lines: List[str]):
    fis = ssg = srg = shuffle = show = one = cant = None
    keep: List[str] = []
    for ln in desc_lines:
        m1 = OPT_HTML_RE.match(ln)
        if m1:
            key, val = m1.group(1).lower(), m1.group(2).lower()
            v = (val == 'true')
            if key == 'feedback is solution':
                fis = v
            elif key == 'solutions sample groups':
                ssg = v
            elif key == 'solutions randomize groups':
                srg = v
            elif key == 'shuffle answers':
                shuffle = v
            elif key == 'show correct answers':
                show = v
            elif key == 'one question at a time':
                one = v
            elif key.startswith('can'):
                cant = v
            continue
        m2 = OPT_LINE_RE.match(ln)
        if m2:
            key, val = m2.group(1).lower(), m2.group(2).lower()
            v = (val == 'true')
            if key == 'feedback is solution':
                fis = v
            elif key == 'solutions sample groups':
                ssg = v
            elif key == 'solutions randomize groups':
                srg = v
            elif key == 'shuffle answers':
                shuffle = v
            elif key == 'show correct answers':
                show = v
            elif key == 'one question at a time':
                one = v
            elif key.startswith('can'):
                cant = v
            continue
        keep.append(ln)
    return (fis, ssg, srg, shuffle, show, one, cant, keep)

# ------------------------------ Helpers ------------------------------

H1_RE = re.compile(r'^\s*#\s+(.*)\s*$')
H2_RE = re.compile(r'^\s*##\s+(.*)\s*$')
POINTS_PAREN_RE = re.compile(r'\(points:\s*([0-9]+(?:\.5)?)\)', re.IGNORECASE)
ATTRS_RE = re.compile(r'\{([^}]*)\}\s*$')
ATTR_PAIR_RE = re.compile(r'\s*([a-zA-Z_]+)\s*=\s*([^,]+)\s*')
TASK_RE = re.compile(r'^\s*-\s*\[( |x|X)\]\s+(.*)$')
BLOCKQUOTE_RE = re.compile(r'^\s*>\s?(.*)$')
ANS_HDR_RE = re.compile(r'^\s*###\s*Answers?\s*:?\s*$', re.IGNORECASE)
NUM_SPEC_RE = re.compile(r'^\s*=\s*(.+?)\s*$')
BULLET_RE = re.compile(r'^\s*-\s+(.*)$')
PREFIX_RE = re.compile(r'^\s*(Correct|Incorrect|General)\s*:\s*(.*)$', re.IGNORECASE)

HTML_SINGLE_RE = re.compile(r'^\s*<!--\s*(.*?)\s*-->\s*$')
HTML_OPEN_RE   = re.compile(r'^\s*<!--\s*$')
HTML_CLOSE_RE  = re.compile(r'^\s*-->\s*$')

def html_comments_to_t2qti(lines: List[str]) -> List[str]:
    """Convert HTML comments in Markdown into text2qti line/block comments.
    - <!-- text --> => % text
    - <!-- ... multiline ... --> => COMMENT ... END_COMMENT
    Non-comment lines are passed through unchanged.
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m_single = HTML_SINGLE_RE.match(ln)
        if m_single:
            out.append(f"% {m_single.group(1)}")
            i += 1
            continue
        if HTML_OPEN_RE.match(ln):
            out.append("COMMENT")
            i += 1
            while i < len(lines) and not HTML_CLOSE_RE.match(lines[i]):
                out.append(lines[i])
                i += 1
            if i < len(lines) and HTML_CLOSE_RE.match(lines[i]):
                i += 1
            out.append("END_COMMENT")
            continue
        out.append(ln)
        i += 1
    return out

def strip_trailing_blank(lines: List[str]) -> List[str]:
    out = list(lines)
    while out and out[-1].strip() == '':
        out.pop()
    return out

def strip_leading_blank(lines: List[str]) -> List[str]:
    out = list(lines)
    while out and out and out[0].strip() == '':
        out.pop(0)
    return out

def strip_surrounding_blank(lines: List[str]) -> List[str]:
    return strip_trailing_blank(strip_leading_blank(lines))

def parse_attrs(title_text: str) -> Tuple[str, Optional[float], Dict[str, str]]:
    """Extract points and {attrs} from the H2 text, return clean title, points, attrs."""
    points = None
    attrs: Dict[str, str] = {}

    # (points: N)
    m_pts = POINTS_PAREN_RE.search(title_text)
    if m_pts:
        try:
            points = float(m_pts.group(1))
        except ValueError:
            raise ValueError(f"Invalid points value in header: {title_text}")
        title_text = POINTS_PAREN_RE.sub('', title_text).strip()

    # { ... }
    m_attrs = ATTRS_RE.search(title_text)
    if m_attrs:
        raw = m_attrs.group(1)
        title_text = ATTRS_RE.sub('', title_text).strip()
        # split by commas not inside quotes (simple split; values shouldn't need commas typically)
        for part in raw.split(','):
            part = part.strip()
            if not part:
                continue
            m = ATTR_PAIR_RE.match(part)
            if not m:
                raise ValueError(f"Invalid attribute '{part}' in header.")
            k, v = m.group(1).lower(), m.group(2).strip()
            # strip optional quotes around value
            if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
                v = v[1:-1]
            attrs[k] = v

        # {points=N} overrides parenthetical
        if 'points' in attrs:
            try:
                points = float(attrs['points'])
            except ValueError:
                raise ValueError(f"Invalid points value in attrs: {attrs['points']}")

    return title_text.strip(), points, attrs

def split_sections(lines: List[str]) -> Tuple[str, List[str], List[Tuple[str, List[str]]]]:
    """Return (quiz_title, description_lines, list of (h2_header_text, body_lines))."""
    i = 0
    title = None
    # find H1
    while i < len(lines):
        m = H1_RE.match(lines[i])
        if m:
            title = m.group(1).strip()
            i += 1
            break
        elif lines[i].strip() == '':
            i += 1
        else:
            # if no H1, treat first nonblank as title anyway
            title = lines[i].strip()
            i += 1
            break
    if title is None:
        title = "Untitled Quiz"

    # capture description until first H2
    desc = []
    while i < len(lines) and not H2_RE.match(lines[i]):
        desc.append(lines[i])
        i += 1
    desc = strip_surrounding_blank(desc)

    # gather H2 sections
    sections = []
    while i < len(lines):
        m = H2_RE.match(lines[i])
        if not m:
            i += 1
            continue
        header = m.group(1).strip()
        i += 1
        start = i
        while i < len(lines) and not H2_RE.match(lines[i]):
            i += 1
        body = lines[start:i]
        sections.append((header, body))

    return title, desc, sections


def parse_question(header_text: str, body_lines: List[str]) -> Item:
    # Extract optional leading number from the H2 header (e.g., "12. Title text")
    m_hdrnum = re.match(r'^\s*(\d+)\.\s+(.*)$', header_text)
    qnum: Optional[int] = None
    if m_hdrnum:
        qnum = int(m_hdrnum.group(1))
        header_text = m_hdrnum.group(2)
    title, points, attrs = parse_attrs(header_text)
    qtype = attrs.get('type', '').lower()
    if not qtype:
        raise ValueError(f"Missing required attribute 'type' in header: '{header_text}'")
    if qtype not in {'mc', 'ma', 'num', 'fill', 'essay', 'file', 'text'}:
        raise ValueError(f"Unsupported type '{qtype}' in header: '{header_text}'")

    # default points
    if points is None and qtype != 'text':
        points = 1.0

    # Split prompt vs answers by cues
    # For mc/ma: find first task list line
    # For num: find "### Answer:" then collect NUM_SPEC line
    # For fill: find "### Answers:" then collect bullets
    body = list(body_lines)

    def first_match_idx(pattern):
        for idx, line in enumerate(body):
            if pattern(line):
                return idx
        return None

    prompt_lines: List[str] = []
    choices: List[Choice] = []
    q_feedback: List[FeedbackBlock] = []
    numeric_spec: Optional[str] = None
    fill_answers: List[str] = []
    trailing_comments: List[str] = []

    if qtype in {'mc', 'ma'}:
        # find first task line
        first_task = first_match_idx(lambda ln: TASK_RE.match(ln) is not None)
        if first_task is None:
            # no choices — everything is prompt (will fail validation later)
            prompt_lines = strip_surrounding_blank(body)
        else:
            prompt_lines = strip_surrounding_blank(body[:first_task])
            # parse choice blocks
            i = first_task
            while i < len(body):
                m_task = TASK_RE.match(body[i])
                if not m_task:
                    # could be question-level feedback or trailing blank
                    break
                checked = (m_task.group(1).lower() == 'x')
                first_text = m_task.group(2)
                choice_lines = [first_text]
                per_choice_fb: List[str] = []
                i += 1
                # consume indented blockquotes as per-choice feedback
                while i < len(body):
                    line = body[i]
                    if BLOCKQUOTE_RE.match(line) and (len(line) - len(line.lstrip())) > 0:
                        # indented blockquote => per-choice
                        m_bq = BLOCKQUOTE_RE.match(line)
                        per_choice_fb.append(m_bq.group(1))
                        i += 1
                        continue
                    # empty lines under choice are allowed; keep them in feedback as blank lines
                    if line.strip() == '' and (i < len(body)-1):
                        if per_choice_fb:
                            per_choice_fb.append('')
                            i += 1
                            continue
                    # If we see an indented non-blockquote line here, it's ambiguous — raise
                    if (len(line) - len(line.lstrip())) > 0 and not BLOCKQUOTE_RE.match(line):
                        raise ValueError(
                            "Unexpected indented non-blockquote under a choice. "
                            "Use an indented blockquote ('> ') for per-choice feedback, "
                            "or keep the choice text to a single line. Offending line: " + line.strip()
                        )
                    break
                choices.append(Choice(text_lines=[first_text], correct=checked, feedback_lines=strip_trailing_blank(per_choice_fb)))
            # after choices and question-level feedback, capture any trailing HTML comments
            trailing: List[str] = []
            while i < len(body):
                ln = body[i]
                # Question-level feedback (top-level blockquotes)
                m_bq = BLOCKQUOTE_RE.match(ln)
                if m_bq:
                    text = m_bq.group(1)
                    kind = 'general'
                    m_pref = PREFIX_RE.match(text)
                    if m_pref:
                        key = m_pref.group(1).lower()
                        payload = m_pref.group(2)
                        if key == 'correct':
                            kind = 'correct'
                        elif key == 'incorrect':
                            kind = 'incorrect'
                        else:
                            kind = 'general'
                        text = payload
                    q_feedback.append(FeedbackBlock(kind=kind, lines=[text] if text != '' else ['']))
                    i += 1
                    continue
                # HTML comments (single or block)
                if HTML_SINGLE_RE.match(ln):
                    # If there was a blank line immediately before this comment, preserve one
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    m = HTML_SINGLE_RE.match(ln)
                    trailing.append(f"% {m.group(1)}")
                    i += 1
                    continue
                if HTML_OPEN_RE.match(ln):
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    trailing.append('COMMENT')
                    i += 1
                    while i < len(body) and not HTML_CLOSE_RE.match(body[i]):
                        trailing.append(body[i])
                        i += 1
                    if i < len(body) and HTML_CLOSE_RE.match(body[i]):
                        i += 1
                    trailing.append('END_COMMENT')
                    continue
                # ignore pure blanks; otherwise raise on stray content
                if ln.strip() == '':
                    i += 1
                    continue
                raise ValueError("Unrecognized content after answers/feedback in MC/MA question: " + ln.strip())
            trailing_comments = trailing

    elif qtype == 'num':
        # find "### Answer:"
        ans_hdr_idx = first_match_idx(lambda ln: ANS_HDR_RE.match(ln) is not None)
        if ans_hdr_idx is None:
            prompt_lines = strip_surrounding_blank(body)
        else:
            prompt_lines = strip_surrounding_blank(body[:ans_hdr_idx])
            # next nonblank after header should be NUM_SPEC
            i = ans_hdr_idx + 1
            while i < len(body) and body[i].strip() == '':
                i += 1
            if i < len(body):
                m_num = NUM_SPEC_RE.match(body[i])
                if m_num:
                    numeric_spec = m_num.group(1).strip()
                    i += 1
                # gather question-level feedback blockquotes
                while i < len(body):
                    m_bq = BLOCKQUOTE_RE.match(body[i])
                    if m_bq:
                        text = m_bq.group(1)
                        kind = 'general'
                        m_pref = PREFIX_RE.match(text)
                        if m_pref:
                            key = m_pref.group(1).lower()
                            payload = m_pref.group(2)
                            if key == 'correct':
                                kind = 'correct'
                            elif key == 'incorrect':
                                kind = 'incorrect'
                            else:
                                kind = 'general'
                            text = payload
                        q_feedback.append(FeedbackBlock(kind=kind, lines=[text] if text != '' else ['']))
                        i += 1
                    else:
                        # stop here so trailing pass can process comments or raise on stray content
                        break
            # capture trailing HTML comments
            trailing: List[str] = []
            while i < len(body):
                ln = body[i]
                if HTML_SINGLE_RE.match(ln):
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    m = HTML_SINGLE_RE.match(ln)
                    trailing.append(f"% {m.group(1)}")
                    i += 1
                    continue
                if HTML_OPEN_RE.match(ln):
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    trailing.append('COMMENT')
                    i += 1
                    while i < len(body) and not HTML_CLOSE_RE.match(body[i]):
                        trailing.append(body[i])
                        i += 1
                    if i < len(body) and HTML_CLOSE_RE.match(body[i]):
                        i += 1
                    trailing.append('END_COMMENT')
                    continue
                if ln.strip() == '':
                    i += 1
                    continue
                raise ValueError("Unrecognized content after numeric spec/feedback in NUM question: " + ln.strip())
            trailing_comments = trailing

    elif qtype == 'fill':
        ans_hdr_idx = first_match_idx(lambda ln: re.match(r'^\s*###\s*Answers?\s*:?\s*$', ln, re.IGNORECASE) is not None)
        if ans_hdr_idx is None:
            prompt_lines = strip_surrounding_blank(body)
        else:
            prompt_lines = strip_surrounding_blank(body[:ans_hdr_idx])
            i = ans_hdr_idx + 1
            # gather bullets
            while i < len(body):
                if body[i].strip() == '':
                    i += 1
                    continue
                m_b = BULLET_RE.match(body[i])
                if not m_b:
                    break
                fill_answers.append(m_b.group(1).strip())
                i += 1
            # question-level feedback
            while i < len(body):
                m_bq = BLOCKQUOTE_RE.match(body[i])
                if m_bq:
                    text = m_bq.group(1)
                    kind = 'general'
                    m_pref = PREFIX_RE.match(text)
                    if m_pref:
                        key = m_pref.group(1).lower()
                        payload = m_pref.group(2)
                        if key == 'correct':
                            kind = 'correct'
                        elif key == 'incorrect':
                            kind = 'incorrect'
                        else:
                            kind = 'general'
                        text = payload
                    q_feedback.append(FeedbackBlock(kind=kind, lines=[text] if text != '' else ['']))
                    i += 1
                else:
                    # stop so trailing pass can process comments or raise on stray content
                    break
            # capture trailing HTML comments
            trailing: List[str] = []
            while i < len(body):
                ln = body[i]
                if HTML_SINGLE_RE.match(ln):
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    m = HTML_SINGLE_RE.match(ln)
                    trailing.append(f"% {m.group(1)}")
                    i += 1
                    continue
                if HTML_OPEN_RE.match(ln):
                    had_blank = (i > 0 and body[i-1].strip() == '')
                    if had_blank and (not trailing or trailing[-1] != ''):
                        trailing.append('')
                    trailing.append('COMMENT')
                    i += 1
                    while i < len(body) and not HTML_CLOSE_RE.match(body[i]):
                        trailing.append(body[i])
                        i += 1
                    if i < len(body) and HTML_CLOSE_RE.match(body[i]):
                        i += 1
                    trailing.append('END_COMMENT')
                    continue
                if ln.strip() == '':
                    i += 1
                    continue
                raise ValueError("Unrecognized content after answers/feedback in FILL question: " + ln.strip())
            trailing_comments = trailing

    else:
        # essay/file/text : prompt only; ignore feedback
        # NEW: enforce that no answers/feedback structures appear here
        for ln in body:
            if TASK_RE.match(ln):
                raise ValueError("Task list (choices) found in a non-choice question (essay/file/text): " + ln.strip())
            if ANS_HDR_RE.match(ln):
                raise ValueError("'### Answers:' section found in a non-fill question (essay/file/text).")
            if BLOCKQUOTE_RE.match(ln):
                raise ValueError("Question-level or per-choice feedback (blockquote) found in essay/file/text question: " + ln.strip())
        prompt_lines = strip_surrounding_blank(body)

    q = Item(
        title=title, kind=qtype, points=points, attrs=attrs,
        prompt_lines=prompt_lines, choices=choices, numeric_spec=numeric_spec,
        fill_answers=fill_answers, q_feedback=q_feedback, qnum=qnum,
        trailing_comments=trailing_comments
    )
    return q

def validate_question(q: Item):
    # Points
    if q.kind != 'text':
        if q.points is None:
            q.points = 1.0
        if q.points < 0:
            raise ValueError(f"Points must be >= 0 in question '{q.title}'.")
        # allow .0 or .5
        if not ((q.points * 2).is_integer()):
            raise ValueError(f"Points must be integer or half-integer in '{q.title}'.")

    if q.kind in {'mc', 'ma'}:
        if not q.choices:
            raise ValueError(f"No choices found for '{q.title}'.")
        n_correct = sum(1 for c in q.choices if c.correct)
        if q.kind == 'mc' and n_correct != 1:
            raise ValueError(f"MC question '{q.title}' must have exactly one [x] choice; found {n_correct}.")
        if q.kind == 'ma' and n_correct < 1:
            raise ValueError(f"MA question '{q.title}' must have at least one [x] choice; found 0.")

    if q.kind == 'num':
        if not q.numeric_spec:
            raise ValueError(f"NUM question '{q.title}' requires a numeric spec line starting with '=' after '### Answer:'.")
        # basic sanity check for allowed formats
        spec = q.numeric_spec.strip()
        ok = False
        if re.match(r'^\[.*?,.*?\]$', spec):  # interval
            ok = True
        elif re.search(r'\+\-\s*[\d.]+(%?)$', spec):  # tolerance with +-
            ok = True
        elif re.match(r'^-?\d+(\.\d+)?$', spec):  # plain number
            ok = True
        if not ok:
            # Still allow text2qti to parse; only warn would be better, but we raise to keep spec strict.
            pass

    if q.kind == 'fill':
        if not q.fill_answers:
            raise ValueError(f"FILL question '{q.title}' requires at least one answer under '### Answers:'.")

def parse_quiz(md_text: str) -> Quiz:
    lines = md_text.splitlines()
    title, desc_lines, sections = split_sections(lines)
    questions: List[Item] = []
    for hdr, body in sections:
        q = parse_question(hdr, body)
        validate_question(q)
        questions.append(q)
    fis, ssg, srg, shuffle, show, one, cant, cleaned = parse_options_from_desc(strip_surrounding_blank(desc_lines))
    return Quiz(title=title, description_lines=cleaned, items=questions,
                feedback_is_solution=fis, solutions_sample_groups=ssg,
                solutions_randomize_groups=srg,
                shuffle_answers=shuffle, show_correct_answers=show,
                one_question_at_a_time=one, cant_go_back=cant)

# ------------------------------ Emission ------------------------------

def emit_wrapped(prefix: str, text: str) -> List[str]:
    """Emit 'prefix + first line' then subsequent lines indented to same level as text2qti expects.
    We do not hard-wrap; we preserve author's wrapping.
    """
    lines = text.splitlines() if '\n' in text else [text]
    out = []
    if lines:
        out.append(f"{prefix}{lines[0]}")
        for ln in lines[1:]:
            # Maintain indent of 4 spaces after markers for continuation
            out.append(f"    {ln}")
    else:
        out.append(prefix.rstrip())
    return out

def md_join(lines: List[str]) -> str:
    return "\n".join(lines).rstrip()

def emit_text2qti(quiz: Quiz) -> str:
    out = []
    # Quiz title & description
    out.append(f"Quiz title: {quiz.title}")

    if quiz.description_lines:
        # Convert HTML comments to text2qti and emit in-order;
        # comments stay top-level; non-comments form the wrapped description body.
        conv = html_comments_to_t2qti(quiz.description_lines)
        started = False
        for ln in conv:
            if ln == 'COMMENT' or ln == 'END_COMMENT' or ln.lstrip().startswith('%'):
                # Emit comments at top-level, preserving order
                out.append(ln)
                continue
            if not started:
                out.append(f"Quiz description: {ln}")
                started = True
            else:
                out.append(f"    {ln}")
        if not started:
            # Empty description
            out.append("Quiz description: ")

    # Emit option lines right after description (no indent), if present
    if quiz.feedback_is_solution is not None:
        out.append(f"feedback is solution: {'true' if quiz.feedback_is_solution else 'false'}")
    if quiz.solutions_sample_groups is not None:
        out.append(f"solutions sample groups: {'true' if quiz.solutions_sample_groups else 'false'}")
    if quiz.solutions_randomize_groups is not None:
        out.append(f"solutions randomize groups: {'true' if quiz.solutions_randomize_groups else 'false'}")
    if quiz.shuffle_answers is not None:
        out.append(f"shuffle answers: {'true' if quiz.shuffle_answers else 'false'}")
    if quiz.show_correct_answers is not None:
        out.append(f"show correct answers: {'true' if quiz.show_correct_answers else 'false'}")
    if quiz.one_question_at_a_time is not None:
        out.append(f"one question at a time: {'true' if quiz.one_question_at_a_time else 'false'}")
    if quiz.cant_go_back is not None:
        out.append(f"can't go back: {'true' if quiz.cant_go_back else 'false'}")
    out.append("")

    for idx, q in enumerate(quiz.items, 1):
        if q.kind == 'text':
            # Text region
            out.append(f"Text title: {q.title}")
            prompt = md_join(q.prompt_lines)
            lines = (prompt.splitlines() if prompt.strip() != "" else [""])
            conv = html_comments_to_t2qti(lines)
            # We emit non-comment lines as part of Text: block; comments at top-level
            text_started = False
            for idx_line, ln in enumerate(conv):
                if ln == 'COMMENT' or ln == 'END_COMMENT' or ln.lstrip().startswith('%'):
                    out.append(ln)
                    continue
                if not text_started:
                    out.append(f"Text: {ln}")
                    text_started = True
                else:
                    out.append(f"    {ln}")
            if not text_started:
                # Empty text block
                out.append("Text: ")
            out.append("")
            continue

        # Regular question
        # Remove any accidental number prefix from Title (MD number lives in q.qnum)
        clean_title = re.sub(r'^\s*\d+\.\s+', '', q.title).strip()
        if clean_title:
            out.append(f"Title: {clean_title}")
        pts = int(q.points) if float(q.points).is_integer() else q.points
        out.append(f"Points: {pts}")
        # Stem with comment handling: emit leading comments before the numbered stem,
        # then first non-comment as the stem line, and remaining lines as continuation
        stem = md_join(q.prompt_lines)
        stem_lines = stem.splitlines() or [""]
        conv_all = html_comments_to_t2qti(stem_lines)

        # Emit leading comments before the numbered stem
        k = 0
        while k < len(conv_all):
            ln = conv_all[k]
            if ln == 'COMMENT' or ln == 'END_COMMENT' or ln.lstrip().startswith('%'):
                out.append(ln)
                k += 1
                continue
            break

        # Use q.qnum if present; else fall back to sequential idx
        stem_num = q.qnum if q.qnum is not None else idx
        first_stem = conv_all[k] if k < len(conv_all) and not (conv_all[k] == 'COMMENT' or conv_all[k] == 'END_COMMENT' or conv_all[k].lstrip().startswith('%')) else ''
        out.append(f"{stem_num}. {first_stem}")
        k = k + 1 if first_stem != '' else k

        # Emit remaining lines: comments top-level, non-comments as indented continuation
        while k < len(conv_all):
            ln = conv_all[k]
            if ln == 'COMMENT' or ln == 'END_COMMENT' or ln.lstrip().startswith('%'):
                out.append(ln)
            else:
                out.append(f"    {ln}")
            k += 1

        if q.kind in {'mc', 'ma'}:
            # Question-level feedback should appear BEFORE the answers
            if q.q_feedback:
                for fb in q.q_feedback:
                    marker = '...'
                    if fb.kind == 'correct':
                        marker = '+'
                    elif fb.kind == 'incorrect':
                        marker = '-'
                    for line in ("\n".join(fb.lines)).splitlines() or [""]:
                        out.append(f"{marker} {line}")

            # Emit choices
            if q.kind == 'mc':
                letters = "abcdefghijklmnopqrstuvwxyz"
                for i, ch in enumerate(q.choices):
                    letter = letters[i] + ")"
                    prefix = f"*{letter} " if ch.correct else f"{letter} "
                    # choice text
                    for j, line in enumerate(ch.text_lines):
                        if j == 0:
                            out.append(f"{prefix}{line}")
                        else:
                            out.append(f"    {line}")
                    # per-choice feedback: lines starting with '... '
                    for fb in ch.feedback_lines:
                        out.append(f"... {fb}")
            else:
                # multiple answer: [ ] and [*]
                for ch in q.choices:
                    marker = "[*]" if ch.correct else "[ ]"
                    out.append(f"{marker} {ch.text_lines[0]}")
                    for ln in ch.text_lines[1:]:
                        out.append(f"    {ln}")
                    for fb in ch.feedback_lines:
                        out.append(f"... {fb}")

        elif q.kind == 'num':
            # Question-level feedback should appear BEFORE the numeric answer spec
            if q.q_feedback:
                for fb in q.q_feedback:
                    marker = '...'
                    if fb.kind == 'correct':
                        marker = '+'
                    elif fb.kind == 'incorrect':
                        marker = '-'
                    for line in ("\n".join(fb.lines)).splitlines() or [""]:
                        out.append(f"{marker} {line}")
            out.append(f"=   {q.numeric_spec}")

        elif q.kind == 'fill':
            # Question-level feedback should appear BEFORE the acceptable answers
            if q.q_feedback:
                for fb in q.q_feedback:
                    marker = '...'
                    if fb.kind == 'correct':
                        marker = '+'
                    elif fb.kind == 'incorrect':
                        marker = '-'
                    for line in ("\n".join(fb.lines)).splitlines() or [""]:
                        out.append(f"{marker} {line}")
            for ans in q.fill_answers:
                out.append(f"*   {ans}")

        elif q.kind == 'essay':
            out.append("____")

        elif q.kind == 'file':
            out.append("^^^^")

        # Emit any trailing top-level comments captured from Markdown
        if getattr(q, 'trailing_comments', None):
            for ln in q.trailing_comments:
                if ln == '':
                    out.append('')
                else:
                    out.append(ln)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Convert Markdown quiz to text2qti plaintext.")
    ap.add_argument("input", help="Input Markdown file")
    ap.add_argument("-o", "--output", help="Output text2qti plaintext file (default: stdout)")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        md = f.read()
    quiz = parse_quiz(md)
    out = emit_text2qti(quiz)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        print(out)

if __name__ == "__main__":
    main()
