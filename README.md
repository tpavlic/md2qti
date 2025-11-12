# md2qti

Convert between a **pure-Markdown quiz format** and **text2qti** plaintext, so you can author Canvas-compatible QTI quizzes in Markdown, preview them anywhere, and still interoperate with [`text2qti`](https://github.com/gpoore/text2qti).

This repo provides:

- `md2t2qti.py` : **Markdown → text2qti**
- `t2qti2md.py` : **text2qti → Markdown**
- Ready-to-use macOS droplets/apps that wrap those scripts for drag-and-drop conversion.

The [`text2qti`](https://github.com/gpoore/text2qti) package has been a valuable tool for streamlining the construction of quizzes for learning management systems like Canvas that support the QTI format. Rather than requiring instructors to build quizzes within the native LMS interface, `text2qti` has enabled managing quizzes offline in a flat format. It has leveraged MarkDown to provide formatting options for quiz questions, answers, and feedback. However, the meta data about quizzes and their questions is encoded in a proprietary format that prevents modern text editors from properly preview or easily share the quizzes with other instructors and teaching staff.

Thus, `md2qti` is meant to provide a wrapper around `text2qti` that embeds all quiz metadata within MarkDown itself. The Markdown schema is deliberately simple and preview friendly. Question metadata (type, points, etc.) are embedded in headers; all prompts and rich content live in normal Markdown (including inline LaTeX with `$...$`, which `text2qti` supports).

---

## Why this exists

- Write quizzes in **one readable file** you can lint, diff, and preview.
- Keep fidelity with **text2qti** while adding stricter validation and better handling of comments, spacing, and multi-line content.
- Support round-trip editing: `Markdown → text2qti → Markdown` with whitespace and comments preserved sensibly.

---

## Features (both directions)

- **Question types**: multiple choice (`mc`), multiple answer (`ma`), numeric (`num`), fill/short-answer (`fill`), essay (`essay`), file upload (`file`), and text regions (`text` stimulus blocks).
- **Question-level feedback**: `Correct`, `Incorrect`, and `General`, placed *after* answers/specs in Markdown and mapped to `...`, `+`, and `-` blocks in text2qti.
- **Per-choice feedback** via indented blockquotes in Markdown.
- **LaTeX**: `$...$` math is passed through.
- **Comments preserved**:
  - text2qti `% line` → `<!-- line -->` in Markdown
  - `COMMENT ... END_COMMENT` → multi-line HTML comment block
  - Spacing around comments is preserved: if the source had a blank line before a comment, the output has one (and only one).
- **Quiz-level options** (after the description):
  `shuffle answers`, `show correct answers`, `one question at a time`, `can't go back`
  Represented as blockquoted lines in Markdown:

  ```markdown
  > shuffle answers: true
  > show correct answers: false
  ...
  ```

- **Strict validation**: malformed input raises clear `ValueError`s with line numbers rather than silently dropping content (e.g., unindented wrapped stems, stray lines after choices, invalid `mc` with more than 1 correct answer).
- **Round-trip friendly**: multi-line prompts/choices/answers preserve intentional blank lines within continuation blocks.

---

## Quick example

Convert a Markdown quiz to Canvas-importable QTI:

```bash
./md2t2qti.py examples/quiz.md -o quiz.txt
text2qti quiz.txt
```

Then import the generated QTI ZIP into your LMS (e.g., Canvas).

> Tip: The `MDtoText2QTI.app` macOS droplet will attempt to do both steps for you in one pass.

---

## Command-line usage

### Markdown → text2qti format

```bash
./md2t2qti.py quiz.md -o quiz.txt
```

- Validates the Markdown schema.
- Emits text2qti plaintext suitable for `text2qti` → QTI packaging.

### text2qti format → Markdown

```bash
./t2qti2md.py quiz.txt -o quiz.md
```

- Validates text2qti structure.
- Preserves comments and spacing semantics.
- Enforces: for MC items there must be exactly one correct choice.

**Errors** are **hard stops** with line numbers (e.g., unindented wrapped stems, stray text after choices, invalid `mc` correctness count).

---

## macOS droplets

Under `macos/` you'll find two `.app` droplet bundles:

- **MDtoText2QTI.app**: drop one or more `.md` files; outputs `.txt` (text2qti)
- **Text2QTI2MD.app**: drop one or more `.txt` (text2qti) files; outputs `.md`

Both bundles include the corresponding Python scripts and AppleScript wrappers.

> Tip: You can also open these in Script Editor via the `.scptd` bundles if you want to tweak behavior.

---

## Future work

- Direct Markdown → QTI XML conversion (bypassing `text2qti`).
  - Incorporation of [`qti-package-maker`](https://pypi.org/project/qti-package-maker/)
  - Support for QTI question types beyond `text2qti`, like matching and ordering questions supported by `qti-package-maker`.
- Unit tests and sample round-trip fixtures.

---

## License

MIT (or similar open license; update as appropriate).
