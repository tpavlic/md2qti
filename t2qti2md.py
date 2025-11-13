#!/usr/bin/env python3
"""
t2qti2md.py — Convert text2qti plaintext back into our Markdown-only quiz schema.

Usage:
    python t2qti2md.py input.txt [-o output.md]
"""
import argparse
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------- Data Models ----------
@dataclass
class QLevelFB:
    general: List[str] = field(default_factory=list)
    correct: List[str] = field(default_factory=list)
    incorrect: List[str] = field(default_factory=list)
    information: List[str] = field(default_factory=list)

@dataclass
class Choice:
    text: List[str]
    correct: bool
    per_feedback: List[str] = field(default_factory=list)

@dataclass
class Item:
    kind: str  # mc, ma, num, fill, essay, file, text
    title: str
    points: Optional[float]
    stem: List[str]
    qfb: QLevelFB = field(default_factory=QLevelFB)
    qnum: Optional[int] = None  # original text2qti question number, if present
    pre_comments: List[str] = field(default_factory=list)   # HTML comments that precede this item
    # type-specific
    choices: List[Choice] = field(default_factory=list)     # mc/ma
    numeric_spec: Optional[str] = None                      # num
    fill_answers: List[str] = field(default_factory=list)   # fill
    post_comments: List[str] = field(default_factory=list)   # comments after this item

@dataclass
class Quiz:
    title: str
    description: List[str]
    items: List[Item]
    feedback_is_solution: Optional[bool] = None
    solutions_sample_groups: Optional[bool] = None
    solutions_randomize_groups: Optional[bool] = None
    shuffle_answers: Optional[bool] = None
    show_correct_answers: Optional[bool] = None
    one_question_at_a_time: Optional[bool] = None
    cant_go_back: Optional[bool] = None


# ---------- Regex to parse text ----------
RE_QTITLE = re.compile(r'^\s*Quiz title:\s*(.*)\s*$')
RE_QDESC = re.compile(r'^\s*Quiz description:\s*(.*)\s*$')
RE_TEXT_TITLE = re.compile(r'^\s*Text title:\s*(.*)\s*$')
RE_TEXT = re.compile(r'^\s*Text:\s*(.*)\s*$')
RE_TITLE = re.compile(r'^\s*Title:\s*(.*)\s*$')
RE_POINTS = re.compile(r'^\s*Points:\s*([0-9]+(?:\.[0-9]+)?)\s*$')
RE_STEM_FIRST = re.compile(r'^\s*([0-9]+)\.\s+(.*)\s*$')
RE_CONT = re.compile(r'^\s{4,}(.*)$')

RE_QFB_GEN = re.compile(r'^\s*\.\.\.\s(.*)\s*$')
RE_QFB_COR = re.compile(r'^\s*\+\s(.*)\s*$')
RE_QFB_INC = re.compile(r'^\s*-\s(.*)\s*$')
RE_QFB_INFO = re.compile(r'^\s*!\s(.*)\s*$')

RE_MC_CHOICE = re.compile(r'^\s*(\*?)([a-z])\)\s(.*)\s*$')
RE_MA_CHOICE = re.compile(r'^\s*(\[\*]|\[\s])\s(.*)\s*$')
RE_PER_CHOICE_FB = re.compile(r'^\s*\.\.\.\s(.*)\s*$')

RE_NUM = re.compile(r'^\s*=\s+(.*)\s*$')
RE_FILL = re.compile(r'^\s*\*\s+(.*)\s*$')
RE_ESSAY = re.compile(r'^\s*____\s*$')
RE_FILE = re.compile(r'^\s*\^\^\^\^\s*$')

# Quiz-level options (7 supported)
RE_OPT = re.compile(r'^\s*(feedback is solution|solutions sample groups|solutions randomize groups|shuffle answers|show correct answers|one question at a time|can\'?t go back)\s*:\s*(true|false)\s*$', re.IGNORECASE)

def _parse_bool(val: str) -> bool:
    return val.strip().lower() == 'true'


# ---------- Strict parse error helper ----------
def _perr(i: int, msg: str) -> None:
    raise ValueError(f"Parse error near line {i+1}: {msg}")


def _dedent_lines(lines: List[str]) -> List[str]:
    # Remove single leading 4-space continuation indent from lines that have it
    out = []
    for ln in lines:
        m = RE_CONT.match(ln)
        out.append(m.group(1) if m else ln.rstrip())
    # drop trailing blanks
    while out and out[-1].strip() == '':
        out.pop()
    # drop leading blanks
    while out and out[0].strip() == '':
        out.pop(0)
    return out

# Convert a single text2qti line comment (starting with '%') to an HTML comment line
def _t2qti_line_to_html(line: str) -> str:
    # remove leading '%' and one optional space
    content = line.lstrip()[1:]
    if content.startswith(' '):
        content = content[1:]
    return f"<!-- {content} -->"

# Parse a COMMENT ... END_COMMENT block starting at index i; return (html_lines, new_index)
def _consume_block_comment(lines: List[str], i: int) -> tuple[List[str], int]:
    html = ["<!--"]
    i += 1  # skip the COMMENT line
    while i < len(lines):
        if lines[i].lstrip().startswith('END_COMMENT'):
            html.append("-->")
            return html, i + 1
        # store raw line content (without any enforced trimming)
        html.append(lines[i])
        i += 1
    # unterminated block: close anyway
    html.append("-->")
    return html, i

# Consume trailing comments and optional preceding blank lines after an item body.
# Returns (html_comments_list, new_index). Inserts '' before a comment if a blank line preceded it in source.
def _consume_trailing_comments(lines: List[str], i: int) -> Tuple[List[str], int]:
    out: List[str] = []
    # tolerate any number of blanks but preserve at most one as a marker before the next comment
    saw_blank = False
    j = i
    while j < len(lines):
        ln = lines[j]
        sln = ln.lstrip()
        if ln.strip() == '':
            saw_blank = True
            j += 1
            continue
        if sln.startswith('%'):
            if saw_blank:
                if not out or out[-1] != '':
                    out.append('')
            out.append(_t2qti_line_to_html(ln))
            saw_blank = False
            j += 1
            # continue to allow another blank/comment sequence
            continue
        if sln.startswith('COMMENT'):
            if saw_blank:
                if not out or out[-1] != '':
                    out.append('')
            block, j2 = _consume_block_comment(lines, j)
            out.extend(block)
            saw_blank = False
            j = j2
            continue
        # next item or other content — stop; do not consume
        break
    return out, j


def parse_text2qti(lines: List[str]) -> Quiz:
    i = 0
    title = ""      # Default title string
    description_accum: List[str] = []
    items: List[Item] = []
    pending_html_comments: List[str] = []

    # Expect Quiz title first
    if i < len(lines) and RE_QTITLE.match(lines[i]):
        title = RE_QTITLE.match(lines[i]).group(1)
        i += 1

    # collect any leading comments before description
    while i < len(lines):
        s = lines[i].lstrip()
        if s.startswith('%'):
            description_accum.append(_t2qti_line_to_html(lines[i]))
            i += 1
        elif s.startswith('COMMENT'):
            html_block, i = _consume_block_comment(lines, i)
            description_accum.extend(html_block)
        else:
            break

    # Optional description
    if i < len(lines) and RE_QDESC.match(lines[i]):
        first = RE_QDESC.match(lines[i]).group(1)
        desc = [first]
        i += 1
        # collect continuation lines (4-space indent), allowing blank lines to be preserved
        while i < len(lines):
            m = RE_CONT.match(lines[i])
            if m:
                desc.append(m.group(1))
                i += 1
                continue
            if lines[i].strip() == '':
                # include a blank only if the next nonblank is another continuation line
                j = i + 1
                while j < len(lines) and lines[j].strip() == '':
                    j += 1
                if j < len(lines) and RE_CONT.match(lines[j]):
                    desc.append('')
                    i += 1
                    continue
                break
            break
        description_accum.extend(_dedent_lines(desc))

        # optionally gather any immediate comments following description
        while i < len(lines):
            s = lines[i].lstrip()
            if s.startswith('%'):
                description_accum.append(_t2qti_line_to_html(lines[i]))
                i += 1
            elif s.startswith('COMMENT'):
                html_block, i = _consume_block_comment(lines, i)
                description_accum.extend(html_block)
            else:
                break

    # Optional quiz-level options (one per line, no indent) — tolerate leading blanks
    opt_fis = opt_ssg = opt_srg = opt_shuffle = opt_show = opt_one = opt_cant = None
    while i < len(lines):
        if lines[i].strip() == '':
            i += 1
            continue
        mopt = RE_OPT.match(lines[i])
        if not mopt:
            break
        key = mopt.group(1).lower()
        val = _parse_bool(mopt.group(2))
        if key == 'feedback is solution':
            opt_fis = val
        elif key == 'solutions sample groups':
            opt_ssg = val
        elif key == 'solutions randomize groups':
            opt_srg = val
        elif key == 'shuffle answers':
            opt_shuffle = val
        elif key == 'show correct answers':
            opt_show = val
        elif key == 'one question at a time':
            opt_one = val
        elif key.startswith("can"):
            opt_cant = val
        i += 1

    # Now parse items
    while i < len(lines):
        ln = lines[i]
        # Skip blanks
        if ln.strip() == '':
            i += 1
            continue
        # Capture standalone comments between items; attach to next item’s stem
        sln = ln.lstrip()
        if sln.startswith('%'):
            # Preserve a single blank line before the comment if present in the source
            if i > 0 and lines[i-1].strip() == '' and (not pending_html_comments or pending_html_comments[-1] != ''):
                pending_html_comments.append('')
            pending_html_comments.append(_t2qti_line_to_html(ln))
            i += 1
            continue
        if sln.startswith('COMMENT'):
            # Preserve a single blank line before the block comment if present in the source
            if i > 0 and lines[i-1].strip() == '' and (not pending_html_comments or pending_html_comments[-1] != ''):
                pending_html_comments.append('')
            html_block, i2 = _consume_block_comment(lines, i)
            pending_html_comments.extend(html_block)
            i = i2
            continue
        # Handle stray quiz-level options that appear here
        mopt_inline = RE_OPT.match(ln)
        if mopt_inline:
            key = mopt_inline.group(1).lower()
            val = _parse_bool(mopt_inline.group(2))
            if key == 'feedback is solution':
                opt_fis = val
            elif key == 'solutions sample groups':
                opt_ssg = val
            elif key == 'solutions randomize groups':
                opt_srg = val
            elif key == 'shuffle answers':
                opt_shuffle = val
            elif key == 'show correct answers':
                opt_show = val
            elif key == 'one question at a time':
                opt_one = val
            elif key.startswith('can'):
                opt_cant = val
            i += 1
            continue

        # Reject anything that’s not a valid item starter at this point
        if not (RE_TEXT_TITLE.match(ln) or RE_TITLE.match(ln) or RE_POINTS.match(ln) or RE_STEM_FIRST.match(ln)):
            _perr(i, "Unexpected content between items; expected 'Text title:', 'Title:', 'Points:', or a numbered stem")

        # Text region
        mtt = RE_TEXT_TITLE.match(ln)
        if mtt:
            t_title = mtt.group(1).strip()
            i += 1
            # Expect Text line
            if i < len(lines) and RE_TEXT.match(lines[i]):
                first = RE_TEXT.match(lines[i]).group(1)
                i += 1
                text_lines = [first]
                while i < len(lines):
                    m = RE_CONT.match(lines[i])
                    if m:
                        text_lines.append(m.group(1))
                        i += 1
                        continue
                    if lines[i].strip() == '':
                        j = i + 1
                        while j < len(lines) and lines[j].strip() == '':
                            j += 1
                        if j < len(lines) and RE_CONT.match(lines[j]):
                            text_lines.append('')
                            i += 1
                            continue
                        break
                    break
            else:
                _perr(i, "Expected 'Text:' line after 'Text title:'")

            # capture any comments immediately following the text block as post-comments
            post_comments, i = _consume_trailing_comments(lines, i)
            items.append(Item(kind='text', title=t_title, points=None,
                              stem=_dedent_lines(text_lines), post_comments=post_comments))
            continue

        # Regular question: optional Title, optional Points, then mandatory numbered Stem
        if not (RE_TITLE.match(ln) or RE_POINTS.match(ln) or RE_STEM_FIRST.match(ln)):
            _perr(i, "Expected 'Title:', 'Points:', or a numbered stem like '1. ...'")
        q_title = ""    # Default title string
        mt = RE_TITLE.match(ln)
        if mt:
            q_title = mt.group(1).strip()
            i += 1
            ln = lines[i] if i < len(lines) else ''

        # Points are optional in this reverse pass; default to 1.0 if absent
        if i < len(lines) and RE_POINTS.match(lines[i]):
            pts = float(RE_POINTS.match(lines[i]).group(1))
            i += 1
        else:
            pts = 1.0

        # Stem first line (capture explicit question number if present)
        qnum = None
        if i < len(lines) and RE_STEM_FIRST.match(lines[i]):
            m_stem = RE_STEM_FIRST.match(lines[i])
            try:
                qnum = int(m_stem.group(1))
            except Exception:
                qnum = None
            stem_first = m_stem.group(2)
            i += 1
        else:
            _perr(i, "Expected a numbered stem like 'N. <prompt>' after Title/Points")
        stem_cont = []
        while i < len(lines):
            m = RE_CONT.match(lines[i])
            if m:
                stem_cont.append(m.group(1))
                i += 1
                continue
            if lines[i].strip() == '':
                j = i + 1
                while j < len(lines) and lines[j].strip() == '':
                    j += 1
                if j < len(lines) and RE_CONT.match(lines[j]):
                    stem_cont.append('')
                    i += 1
                    continue
                break
            # Non-blank and not an indented continuation: only allowed if it begins a valid section
            next_ln = lines[i]
            allowed = (
                RE_QFB_GEN.match(next_ln) or RE_QFB_COR.match(next_ln) or RE_QFB_INC.match(next_ln) or
                RE_NUM.match(next_ln) or RE_ESSAY.match(next_ln) or RE_FILE.match(next_ln) or
                RE_MC_CHOICE.match(next_ln) or RE_MA_CHOICE.match(next_ln) or RE_FILL.match(next_ln)
            )
            if not allowed:
                _perr(i, "Unindented line encountered inside stem; continuation lines must be indented 4+ spaces")
            break
        stem = [stem_first] + stem_cont
        stem = _dedent_lines(stem)

        # collect any comments immediately after the stem (before feedback/answers)
        while i < len(lines):
            s = lines[i].lstrip()
            if s.startswith('%'):
                stem.append(_t2qti_line_to_html(lines[i]))
                i += 1
                continue
            if s.startswith('COMMENT'):
                html_block, i = _consume_block_comment(lines, i)
                stem.extend(html_block)
                continue
            break

        # Question-level feedback BEFORE answers (may be none)
        qfb = QLevelFB()
        lookahead = True
        while i < len(lines) and lookahead:
            if RE_QFB_GEN.match(lines[i]):
                qfb.general.append(RE_QFB_GEN.match(lines[i]).group(1))
                i += 1
            elif RE_QFB_COR.match(lines[i]):
                qfb.correct.append(RE_QFB_COR.match(lines[i]).group(1))
                i += 1
            elif RE_QFB_INC.match(lines[i]):
                qfb.incorrect.append(RE_QFB_INC.match(lines[i]).group(1))
                i += 1
            elif RE_QFB_INFO.match(lines[i]):
                qfb.information.append(RE_QFB_INFO.match(lines[i]).group(1))
                i += 1
            else:
                lookahead = False

        # NUMERIC: question-level feedback before the numeric spec
        if i < len(lines) and (RE_QFB_GEN.match(lines[i]) or RE_QFB_COR.match(lines[i]) or
                               RE_QFB_INC.match(lines[i]) or RE_QFB_INFO.match(lines[i]) or RE_NUM.match(lines[i])):
            # consume feedback first
            while i < len(lines):
                if RE_QFB_GEN.match(lines[i]):
                    qfb.general.append(RE_QFB_GEN.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_COR.match(lines[i]):
                    qfb.correct.append(RE_QFB_COR.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INC.match(lines[i]):
                    qfb.incorrect.append(RE_QFB_INC.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INFO.match(lines[i]):
                    qfb.information.append(RE_QFB_INFO.match(lines[i]).group(1)); i += 1; continue
                break
            # now the spec is required
            if i < len(lines) and RE_NUM.match(lines[i]):
                numeric_spec = RE_NUM.match(lines[i]).group(1).strip()
                i += 1
            else:
                _perr(i, "Expected numeric answer line '= ...' after question-level feedback.")
            post_comments, i = _consume_trailing_comments(lines, i)
            items.append(Item(kind='num', title=q_title, points=pts, stem=stem, qfb=qfb, qnum=qnum,
                              pre_comments=pending_html_comments, numeric_spec=numeric_spec, post_comments=post_comments))
            pending_html_comments = []
            continue

        # ESSAY: feedback/information before the terminator
        if i < len(lines):
            while i < len(lines) and (RE_QFB_GEN.match(lines[i]) or RE_QFB_COR.match(lines[i]) or
                                      RE_QFB_INC.match(lines[i]) or RE_QFB_INFO.match(lines[i])):
                if RE_QFB_GEN.match(lines[i]):    qfb.general.append(RE_QFB_GEN.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_COR.match(lines[i]):    qfb.correct.append(RE_QFB_COR.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INC.match(lines[i]):    qfb.incorrect.append(RE_QFB_INC.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INFO.match(lines[i]):   qfb.information.append(RE_QFB_INFO.match(lines[i]).group(1)); i += 1; continue
            if i < len(lines) and RE_ESSAY.match(lines[i]):
                i += 1
                post_comments, i = _consume_trailing_comments(lines, i)
                items.append(Item(kind='essay', title=q_title, points=pts, stem=stem, qfb=qfb, qnum=qnum,
                                  pre_comments=pending_html_comments, post_comments=post_comments))
                pending_html_comments = []
                continue

        # FILE
        if i < len(lines):
            while i < len(lines) and (RE_QFB_GEN.match(lines[i]) or RE_QFB_COR.match(lines[i]) or
                                      RE_QFB_INC.match(lines[i]) or RE_QFB_INFO.match(lines[i])):
                if RE_QFB_GEN.match(lines[i]):    qfb.general.append(RE_QFB_GEN.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_COR.match(lines[i]):    qfb.correct.append(RE_QFB_COR.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INC.match(lines[i]):    qfb.incorrect.append(RE_QFB_INC.match(lines[i]).group(1)); i += 1; continue
                if RE_QFB_INFO.match(lines[i]):   qfb.information.append(RE_QFB_INFO.match(lines[i]).group(1)); i += 1; continue
            if i < len(lines) and RE_FILE.match(lines[i]):
                i += 1
                post_comments, i = _consume_trailing_comments(lines, i)
                items.append(Item(kind='file', title=q_title, points=pts, stem=stem, qfb=qfb, qnum=qnum,
                                  pre_comments=pending_html_comments, post_comments=post_comments))
                pending_html_comments = []
                continue

        # Multiple-choice or multiple-answer
        choices: List[Choice] = []
        if i < len(lines) and (RE_MC_CHOICE.match(lines[i]) or RE_MA_CHOICE.match(lines[i])):
            mode = 'mc' if RE_MC_CHOICE.match(lines[i]) else 'ma'
            choices_start_i = i
            while i < len(lines):
                if mode == 'mc':
                    mmc = RE_MC_CHOICE.match(lines[i])
                    if not mmc:
                        # allow transition to MA choice (shouldn't happen), feedback, numeric/essay/file/fill,
                        # comments (% or COMMENT...), blank, or next item
                        nxt = lines[i]
                        sln = nxt.lstrip()
                        if (nxt.strip() == '' or RE_QFB_GEN.match(nxt) or RE_QFB_COR.match(nxt) or RE_QFB_INC.match(nxt) or
                            RE_NUM.match(nxt) or RE_ESSAY.match(nxt) or RE_FILE.match(nxt) or RE_MA_CHOICE.match(nxt) or RE_FILL.match(nxt) or
                            RE_TITLE.match(nxt) or RE_TEXT_TITLE.match(nxt) or RE_STEM_FIRST.match(nxt) or
                            sln.startswith('%') or sln.startswith('COMMENT')):
                            break
                        _perr(i, "Unrecognized line after MC choice; expected next choice, feedback, comment, or next section")
                    correct = (mmc.group(1) == '*')
                    text = [mmc.group(3)]
                    i += 1
                    # capture continuation lines for the choice text (≥4 spaces) and preserve blank lines
                    while i < len(lines):
                        mcont = RE_CONT.match(lines[i])
                        if mcont:
                            text.append(mcont.group(1))
                            i += 1
                            continue
                        if lines[i].strip() == '':
                            j = i + 1
                            while j < len(lines) and lines[j].strip() == '':
                                j += 1
                            if j < len(lines) and RE_CONT.match(lines[j]):
                                text.append('')
                                i += 1
                                continue
                            break
                        break
                    # per-choice feedback lines (leading '... ')
                    pc_fb = []
                    while i < len(lines) and RE_PER_CHOICE_FB.match(lines[i]):
                        pc_fb.append(RE_PER_CHOICE_FB.match(lines[i]).group(1))
                        i += 1
                    choices.append(Choice(text=text, correct=correct, per_feedback=pc_fb))
                else:
                    mma = RE_MA_CHOICE.match(lines[i])
                    if not mma:
                        nxt = lines[i]
                        sln = nxt.lstrip()
                        if (nxt.strip() == '' or RE_QFB_GEN.match(nxt) or RE_QFB_COR.match(nxt) or RE_QFB_INC.match(nxt) or
                            RE_NUM.match(nxt) or RE_ESSAY.match(nxt) or RE_FILE.match(nxt) or RE_MC_CHOICE.match(nxt) or RE_FILL.match(nxt) or
                            RE_TITLE.match(nxt) or RE_TEXT_TITLE.match(nxt) or RE_STEM_FIRST.match(nxt) or
                            sln.startswith('%') or sln.startswith('COMMENT')):
                            break
                        _perr(i, "Unrecognized line after MA choice; expected next choice, feedback, comment, or next section")
                    correct = (mma.group(1) == '[*]')
                    text = [mma.group(2)]
                    i += 1
                    # capture continuation lines for the choice text (≥4 spaces) and preserve blank lines
                    while i < len(lines):
                        mcont = RE_CONT.match(lines[i])
                        if mcont:
                            text.append(mcont.group(1))
                            i += 1
                            continue
                        if lines[i].strip() == '':
                            j = i + 1
                            while j < len(lines) and lines[j].strip() == '':
                                j += 1
                            if j < len(lines) and RE_CONT.match(lines[j]):
                                text.append('')
                                i += 1
                                continue
                            break
                        break
                    pc_fb = []
                    while i < len(lines) and RE_PER_CHOICE_FB.match(lines[i]):
                        pc_fb.append(RE_PER_CHOICE_FB.match(lines[i]).group(1))
                        i += 1
                    choices.append(Choice(text=text, correct=correct, per_feedback=pc_fb))

            # Validate MC has exactly one correct answer
            if mode == 'mc':
                n_correct = sum(1 for ch in choices if ch.correct)
                if n_correct != 1:
                    _perr(choices_start_i, f"Multiple-choice question must have exactly one correct answer; found {n_correct}.")
            kind = 'mc' if mode == 'mc' else 'ma'
            # Capture any trailing comments immediately following this item
            post_comments, i = _consume_trailing_comments(lines, i)
            items.append(Item(kind=kind, title=q_title, points=pts, stem=stem, qfb=qfb, qnum=qnum,
                              pre_comments=pending_html_comments, choices=choices, post_comments=post_comments))
            pending_html_comments = []
            continue

        # FILL: feedback block first, then acceptable answers
        fill_answers: List[str] = []
        consumed_fb = False
        while i < len(lines) and (RE_QFB_GEN.match(lines[i]) or RE_QFB_COR.match(lines[i]) or RE_QFB_INC.match(lines[i]) or RE_QFB_INFO.match(lines[i])):
            consumed_fb = True
            if RE_QFB_GEN.match(lines[i]):     qfb.general.append(RE_QFB_GEN.match(lines[i]).group(1)); i += 1; continue
            if RE_QFB_COR.match(lines[i]):     qfb.correct.append(RE_QFB_COR.match(lines[i]).group(1)); i += 1; continue
            if RE_QFB_INC.match(lines[i]):     qfb.incorrect.append(RE_QFB_INC.match(lines[i]).group(1)); i += 1; continue
            if RE_QFB_INFO.match(lines[i]):    qfb.information.append(RE_QFB_INFO.match(lines[i]).group(1)); i += 1; continue
        while i < len(lines) and RE_FILL.match(lines[i]):
            fill_answers.append(RE_FILL.match(lines[i]).group(1))
            i += 1
        if fill_answers or consumed_fb:
            post_comments, i = _consume_trailing_comments(lines, i)
            items.append(Item(kind='fill', title=q_title, points=pts, stem=stem, qfb=qfb, qnum=qnum,
                              pre_comments=pending_html_comments, fill_answers=fill_answers, post_comments=post_comments))
            pending_html_comments = []
            continue

        # Nothing matched for this question body — this is malformed
        _perr(i, "Unrecognized question body: expected choices, numeric '=', fill answers '*', essay '____', or file '^^^^'")

    return Quiz(title=title, description=description_accum, items=items,
                feedback_is_solution=opt_fis, solutions_sample_groups=opt_ssg,
                solutions_randomize_groups=opt_srg,
                shuffle_answers=opt_shuffle, show_correct_answers=opt_show,
                one_question_at_a_time=opt_one, cant_go_back=opt_cant)


 # Ensure exactly one blank line before the next emitted section
def _ensure_blank(out: List[str]):
    if out and out[-1] != "":
        out.append("")

# Collapse trailing blank lines to exactly one
def _collapse_trailing_blanks(out: List[str]):
    # Remove extra blank lines at the end, keeping at most one
    while len(out) >= 2 and out[-1] == "" and out[-2] == "":
        out.pop()

def emit_markdown(q: Quiz) -> str:
    out = []
    # Title
    out.append(f"# {q.title}")
    out.append("")
    # Description
    if q.description:
        out.extend(q.description)
        out.append("")
    # Optional quiz-level options as readable blockquotes after description
    opts = []
    if q.feedback_is_solution is not None:
        opts.append(f"> feedback is solution: {'true' if q.feedback_is_solution else 'false'}")
    if q.solutions_sample_groups is not None:
        opts.append(f"> solutions sample groups: {'true' if q.solutions_sample_groups else 'false'}")
    if q.solutions_randomize_groups is not None:
        opts.append(f"> solutions randomize groups: {'true' if q.solutions_randomize_groups else 'false'}")
    if q.shuffle_answers is not None:
        opts.append(f"> shuffle answers: {'true' if q.shuffle_answers else 'false'}")
    if q.show_correct_answers is not None:
        opts.append(f"> show correct answers: {'true' if q.show_correct_answers else 'false'}")
    if q.one_question_at_a_time is not None:
        opts.append(f"> one question at a time: {'true' if q.one_question_at_a_time else 'false'}")
    if q.cant_go_back is not None:
        opts.append(f"> can't go back: {'true' if q.cant_go_back else 'false'}")
    if opts:
        out.extend(opts)
        out.append("")
    # Items
    for it in q.items:
        if it.kind == 'text':
            out.append(f"## {it.title} {{type=text}}")
            out.append("")  # blank line after heading
            out.extend(it.stem)
            if getattr(it, 'post_comments', None):
                # Emit post-comments directly; if the source had a blank before the comment,
                # the first element will be '' and will render as a blank line.
                for ln in it.post_comments:
                    out.append(ln)
                # After comments, ensure exactly one blank line before the next header
                _ensure_blank(out)
                _collapse_trailing_blanks(out)
            else:
                # No comments; ensure exactly one blank after the text region
                _ensure_blank(out)
                _collapse_trailing_blanks(out)
            continue

        # Any comments that precede this item appear before the header
        if getattr(it, "pre_comments", None):
            if it.pre_comments:
                # Pre-comments may include explicit '' entries to represent a preserved blank line.
                # Extend directly without forcing an extra blank.
                out.extend(it.pre_comments)
        _collapse_trailing_blanks(out)
        # Header
        pts = it.points if it.points is not None else 0
        pts_str = int(pts) if float(pts).is_integer() else pts
        if it.title:
            header_title = f"{it.title} "
        else:
            header_title = ""
        if getattr(it, "qnum", None) is not None:
            header_title = f"{it.qnum}. {header_title}"
        out.append(f"## {header_title}(points: {pts_str}) " + "{type=" + it.kind + "}")
        out.append("")
        # Stem
        out.extend(it.stem)
        out.append("")

        # Type-specific
        if it.kind in {'mc', 'ma'}:
            for ch in it.choices:
                box = "[x]" if ch.correct else "[ ]"
                out.append(f"- {box} {ch.text[0]}")
                # emit continuation lines of choice text, preserving blanks
                for ln in ch.text[1:]:
                    out.append(f"  {ln}")
                # per-choice feedback as indented blockquotes
                for fb in ch.per_feedback:
                    out.append(f"  > {fb}")
            # Add a single blank line before feedback (avoid double blanks)
            if it.qfb.general or it.qfb.incorrect or it.qfb.correct:
                _ensure_blank(out)
            # All question-level feedback AFTER answers/specs — order: Correct, Incorrect, General
            if it.qfb.correct:
                for ln in it.qfb.correct:
                    out.append(f"> Correct: {ln}")
            if it.qfb.incorrect:
                for ln in it.qfb.incorrect:
                    out.append(f"> Incorrect: {ln}")
            if it.qfb.general:
                for ln in it.qfb.general:
                    out.append(f"> General: {ln}")
            if it.qfb.information:
                for ln in it.qfb.information:
                    out.append(f"> Information: {ln}")
            # Emit comments that followed this question in the source
            if getattr(it, 'post_comments', None):
                # Do NOT force a blank here; if the source had a blank before the comment,
                # the first element of post_comments will be '' and will render as a blank line.
                for ln in it.post_comments:
                    out.append(ln)
                # After comments, ensure exactly one blank line before the next header
                _ensure_blank(out)
                _collapse_trailing_blanks(out)
            else:
                out.append("")
                _collapse_trailing_blanks(out)
            continue
        elif it.kind == 'num':
            _ensure_blank(out)           # one blank line before heading
            out.append("### Answer")
            out.append("")              # one blank after heading
            out.append(f"= {it.numeric_spec}")
            # Add a single blank line before feedback (avoid double blanks)
            if it.qfb.general or it.qfb.incorrect or it.qfb.correct:
                _ensure_blank(out)
            # All question-level feedback AFTER answers/specs — order: Correct, Incorrect, General
            if it.qfb.correct:
                for ln in it.qfb.correct:
                    out.append(f"> Correct: {ln}")
            if it.qfb.incorrect:
                for ln in it.qfb.incorrect:
                    out.append(f"> Incorrect: {ln}")
            if it.qfb.general:
                for ln in it.qfb.general:
                    out.append(f"> General: {ln}")
            if it.qfb.information:
                for ln in it.qfb.information:
                    out.append(f"> Information: {ln}")
            if getattr(it, 'post_comments', None):
                for ln in it.post_comments:
                    out.append(ln)
                _ensure_blank(out)
                _collapse_trailing_blanks(out)
            else:
                out.append("")
                _collapse_trailing_blanks(out)
            continue
        elif it.kind == 'fill':
            _ensure_blank(out)           # one blank line before heading
            out.append("### Answers")
            out.append("")              # one blank after heading
            for ans in it.fill_answers:
                out.append(f"- {ans}")
            # Add a single blank line before feedback (avoid double blanks)
            if it.qfb.general or it.qfb.incorrect or it.qfb.correct:
                _ensure_blank(out)
            # All question-level feedback AFTER answers/specs — order: Correct, Incorrect, General
            if it.qfb.correct:
                for ln in it.qfb.correct:
                    out.append(f"> Correct: {ln}")
            if it.qfb.incorrect:
                for ln in it.qfb.incorrect:
                    out.append(f"> Incorrect: {ln}")
            if it.qfb.general:
                for ln in it.qfb.general:
                    out.append(f"> General: {ln}")
            if it.qfb.information:
                for ln in it.qfb.information:
                    out.append(f"> Information: {ln}")
            if getattr(it, 'post_comments', None):
                for ln in it.post_comments:
                    out.append(ln)
                _ensure_blank(out)
                _collapse_trailing_blanks(out)
            else:
                out.append("")
                _collapse_trailing_blanks(out)
            continue
        elif it.kind == 'essay':
            # Feedback after stem
            if it.qfb.correct or it.qfb.incorrect or it.qfb.general or it.qfb.information:
                _ensure_blank(out)
                if it.qfb.correct:
                    for ln in it.qfb.correct:   out.append(f"> Correct: {ln}")
                if it.qfb.incorrect:
                    for ln in it.qfb.incorrect: out.append(f"> Incorrect: {ln}")
                if it.qfb.general:
                    for ln in it.qfb.general:   out.append(f"> General: {ln}")
                if it.qfb.information:
                    for ln in it.qfb.information:    out.append(f"> Information: {ln}")
        elif it.kind == 'file':
            if it.qfb.correct or it.qfb.incorrect or it.qfb.general or it.qfb.information:
                _ensure_blank(out)
                if it.qfb.correct:
                    for ln in it.qfb.correct:   out.append(f"> Correct: {ln}")
                if it.qfb.incorrect:
                    for ln in it.qfb.incorrect: out.append(f"> Incorrect: {ln}")
                if it.qfb.general:
                    for ln in it.qfb.general:   out.append(f"> General: {ln}")
                if it.qfb.information:
                    for ln in it.qfb.information:    out.append(f"> Information: {ln}")
        # For essay/file and any other fallthrough, emit post_comments if present
        if getattr(it, 'post_comments', None):
            for ln in it.post_comments:
                out.append(ln)
            _ensure_blank(out)
            _collapse_trailing_blanks(out)
        else:
            # For essay/file and any other fallthrough, ensure we don't end up with double blanks
            _collapse_trailing_blanks(out)

    # Strip all trailing newlines
    text = "\n".join(out)
    text = text.rstrip("\n")
    return text


def main():
    ap = argparse.ArgumentParser(description="Convert text2qti plaintext to Markdown quiz format.")
    ap.add_argument("input", help="Input text2qti plaintext file")
    ap.add_argument("-o", "--output", help="Output Markdown file (default: stdout)")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    quiz = parse_text2qti(lines)
    md = emit_markdown(quiz)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)


if __name__ == "__main__":
    main()
