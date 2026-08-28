# sat-score-reader

Reads College Board SAT/PSAT practice-test PDFs into structured scores.
Shared by [tpa](https://github.com/dannypernik/tpa) and
[openpath](https://github.com/dannypernik/openpath), which previously each
carried their own copy of this module and hand-applied every fix twice.

## Install

Pin a tag; don't track a branch:

```
sat-score-reader @ git+ssh://git@github.com/dannypernik/sat-score-reader@v1.0.0
```

## Use

```python
from sat_score_reader import get_all_data

data = get_all_data(report_path, details_path)
data['student_name']            # 'Ada Lovelace'
data['rw_score'], data['math_score'], data['total_score']
data['answers']['math']['1']['11']
# {'correct_answer': '14', 'student_answer': '-4', 'is_correct': True}
```

The two paths may be passed in either order.

### Output

| Key | Meaning |
|---|---|
| `test_code`, `test_display_name`, `date` | `'sat8'`, `'SAT 8'`, `'2025.02.28'` |
| `student_name` | from the report PDF |
| `rw_score`, `math_score`, `total_score` | scaled scores from the report PDF |
| `is_rw_found`, `is_math_found` | whether the details export covered that section |
| `is_rw_hard`, `is_math_hard` | which Module 2 the adaptive test routed to |
| `rw_questions_answered`, `math_questions_answered` | non-omitted counts |
| `has_omits` | any question left blank |
| `answers[subject][module][question]` | `correct_answer`, `student_answer`, `is_correct` |
| `answer_key_mismatches` | parsed key differs from the stored one |
| `missing_data` | rows a present section failed to yield |

`get_student_answers(details_path)` alone returns everything except the
report-PDF fields, and returns the string `"invalid"` if the file isn't a
details export.

## Things worth knowing before changing this

**Correctness comes from the PDF's Correct/Incorrect/Omitted word, never from
comparing `student_answer` to `correct_answer`.** Grid-ins accept several forms
of one value (`11/4`, `2.75`) and sometimes several distinct values; the stored
keys hold only the first form CB lists. A student can answer `-4` to a question
keyed `14` and be correct.

**Rows are reconstructed from word bounding boxes, not pdfplumber's
line-clustered text.** Wrapped Domain cells and stacked grid-in answer forms
otherwise share a y-coordinate with neighbouring rows and scramble the output,
including across a page break.

**Columns are located by where their contents recur, not by fixed offsets.**
The Question and Section columns are found as the x0 where their values cluster
once per row. The subject must be read from the Section cell specifically: each
page repeats a filter row containing the bare word `Math`, and the Domain column
contains `Advanced Math` — matching either one relabels the export from its
first row and silently drops a whole section.

**A section that is present must be substantially complete** (`MIN_RW_QUESTIONS`,
`MIN_MATH_QUESTIONS`); one that is absent is fine. An export may cover Reading
and Writing alone or Math alone, but not neither. `is_rw_found`/`is_math_found`
count rows *seen*, so a section whose rows all failed to parse is still rejected
rather than passing as a legitimate single-section export.

## Tests

```
pip install -e '.[dev]' && pytest
```

Real score PDFs are student data and are never committed, so the suite covers
the pure logic. Parser changes should additionally be run against real exports.
