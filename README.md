# md2qti

- [Why this exists](#why-this-exists)
- [Features: QTI question support, comment support, and validation](#features-qti-question-support-comment-support-and-validation)
- [Quick usage example](#quick-usage-example)
- [Markdown question format examples](#markdown-question-format-examples)
  - [Multiple choice (`{type=mc}`)](#multiple-choice-typemc)
  - [Multiple answer (`{type=ma}`)](#multiple-answer-typema)
  - [Numeric (`{type=num}`)](#numeric-typenum)
  - [Short answer (`{type=fill}`)](#short-answer-typefill)
  - [Essay (`{type=essay}`)](#essay-typeessay)
  - [File upload (`{type=file}`)](#file-upload-typefile)
  - [Text region for instructions and stimuli (`{type=text}`)](#text-region-for-instructions-and-stimuli-typetext)
- [Command-line usage](#command-line-usage)
  - [Markdown → text2qti format](#markdown--text2qti-format)
  - [text2qti format → Markdown](#text2qti-format--markdown)
- [macOS droplets](#macos-droplets)
- [Future work](#future-work)
- [License](#license)

Convert between a **pure-Markdown quiz format** and **text2qti** plaintext so you can author Canvas-compatible QTI quizzes in Markdown, preview them anywhere, and still interoperate with [`text2qti`](https://github.com/gpoore/text2qti).

- [Why this exists](#why-this-exists)

This repo provides:

- `md2t2qti.py` : **Markdown → text2qti**
- `t2qti2md.py` : **text2qti → Markdown**
- Ready-to-use macOS droplets/apps that wrap those scripts for drag-and-drop conversion.

The [`text2qti`](https://github.com/gpoore/text2qti) package has been a valuable tool for streamlining the construction of quizzes for learning management systems like Canvas that support the QTI format. Rather than requiring instructors to build quizzes within the native LMS interface, `text2qti` has enabled managing quizzes offline in a flat format. It has leveraged MarkDown to provide formatting options for quiz questions, answers, and feedback. However, the meta data about quizzes and their questions is encoded in a proprietary format that prevents modern text editors from properly preview or easily share the quizzes with other instructors and teaching staff.

Thus, `md2qti` is meant to provide a wrapper around `text2qti` that embeds all quiz metadata within MarkDown itself. The Markdown schema is deliberately simple and preview friendly. Question metadata (type, points, etc.) are embedded in headers; all prompts and rich content live in normal Markdown (including inline LaTeX with `$...$`, which `text2qti` supports).

---

## Why this exists

- Write quizzes in **one readable MarkDown file** you can lint, diff, and preview.
- Keep fidelity with **`text2qti`** while adding stricter validation and better handling of comments, spacing, and multi-line content.
- Support round-trip editing: `Markdown → text2qti → Markdown` with whitespace and comments preserved sensibly.

---

## Features: QTI question support, comment support, and validation

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

## Quick usage example

Convert a Markdown quiz to Canvas-importable QTI:

```bash
./md2t2qti.py examples/quiz.md -o quiz.txt
text2qti quiz.txt
```

Then import the generated QTI ZIP into your LMS (e.g., Canvas).

> Tip: The `MDtoText2QTI.app` macOS droplet will attempt to do both steps for you in one pass.

---

## Markdown question format examples

Below are examples of all supported question types in the pure-Markdown format used by `md2qti`.

### Multiple choice (`{type=mc}`)

```markdown
## 1. Basic addition (points: 1) {type=mc}

What is $2+3$?

- [ ] 4
  > Too low.
- [x] 5
- [ ] 6
  > Too high.

> Correct: Well done!
> Incorrect: Try adding again.
```

### Multiple answer (`{type=ma}`)

```markdown
## 2. Dinosaurs (points: 2) {type=ma}

Which of the following are dinosaurs?

- [ ] Mammoth
  > A mammoth is not a dinosaur. It is an elephant-like mammal.
- [x] *Tyrannosaurus rex*
  > This dinosaur was a carnivore too.
- [x] Triceratops
- [ ] *Smilodon fatalis*
  > _Smilodon_ is the genus for saber-toothed cats.

> General: To understand these answers, look up the precise definition of a dinosaur.
```

### Numeric (`{type=num}`)

```markdown
## 3. Square root (points: 1) {type=num}

What is $\sqrt{2}$?

### Answer

= 1.4142 +- 0.0001
```

### Short answer (`{type=fill}`)

```markdown
## 4. North Pole resident (points: 1) {type=fill}

Who lives at the North Pole?

### Answers

- Santa
- Santa Claus
```

### Essay (`{type=essay}`)

```markdown
## 5. Essay on selection (points: 5) {type=essay}

Explain how natural selection influences quantitative traits.
```

### File upload (`{type=file}`)

```markdown
## 6. Upload figure (points: 1) {type=file}

Upload your plot as a single PDF.
```

### Text region for instructions and stimuli (`{type=text}`)

```markdown
## Formulas {type=text}

You may find the following formulas useful:

* p + q = 1
* h² = Vₐ / Vₚ
```

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

Prebuilt **macOS droplet apps** are available as release assets.

- **MDtoText2QTI.app** — Drop one or more `.md` quiz files to generate `.txt` (text2qti) output automatically.
- **Text2QTI2MD.app** — Drop one or more `.txt` (text2qti) files to convert back to `.md`.

Each app bundles the relevant Python and AppleScript code used in this repository.
You can download the latest versions from the [Releases](https://github.com/tpavlic/md2qti/releases) page.

> Developers: If you’d like to build the apps yourself, see `macos/build_macos.sh`, which packages and signs both droplets for distribution.

---

## Future work

- Direct Markdown → QTI XML conversion (bypassing `text2qti`).
  - Incorporation of [`qti-package-maker`](https://pypi.org/project/qti-package-maker/)
  - Support for QTI question types beyond `text2qti`, like matching and ordering questions supported by `qti-package-maker`.
- Unit tests and sample round-trip fixtures.

---

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2025 Theodore P. Pavlic.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the conditions in the [LICENSE](LICENSE) file.
