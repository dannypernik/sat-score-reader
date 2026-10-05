"""Completeness rules, answer-key checking, and name extraction.

Real score PDFs are student data and are never committed, so these exercise
the pure logic rather than the pdfplumber parse.
"""

import pytest

from sat_score_reader import (
    MIN_ANSWERED,
    MIN_MATH_QUESTIONS,
    MIN_RW_QUESTIONS,
    check_answer_key,
    check_completeness,
    parse_student_name,
)


def _details(is_rw_found=True, is_math_found=True, rw_answered=54, math_answered=44):
    return {
        'is_rw_found': is_rw_found,
        'is_math_found': is_math_found,
        'rw_questions_answered': rw_answered,
        'math_questions_answered': math_answered,
    }


def _totals(rw=54, math=44):
    return {'rw': rw, 'math': math}


# --- both sections present ----------------------------------------------------

def test_complete_export_passes():
    check_completeness(_details(), _totals())


def test_full_export_at_exactly_the_thresholds_passes():
    check_completeness(_details(), _totals(rw=MIN_RW_QUESTIONS, math=MIN_MATH_QUESTIONS))


# --- single-section exports ---------------------------------------------------

def test_math_only_export_passes():
    """A student may submit Math alone; the absent RW section is not an error."""
    check_completeness(
        _details(is_rw_found=False, rw_answered=0), _totals(rw=0))


def test_rw_only_export_passes():
    check_completeness(
        _details(is_math_found=False, math_answered=0), _totals(math=0))


def test_neither_section_found_is_rejected():
    with pytest.raises(ValueError, match='no questions found'):
        check_completeness(
            _details(is_rw_found=False, is_math_found=False, rw_answered=0, math_answered=0),
            _totals(rw=0, math=0))


# --- a section that IS present must be substantially complete -----------------

def test_present_but_partial_rw_is_rejected():
    """The failure mode the presence flag exists to catch: RW rows were in the
    PDF but mostly failed to parse. Without is_rw_found this is indistinguishable
    from a Math-only export and would silently produce a report missing RW."""
    with pytest.raises(ValueError, match='missing RW questions'):
        check_completeness(_details(), _totals(rw=MIN_RW_QUESTIONS - 1))


def test_present_but_partial_math_is_rejected():
    with pytest.raises(ValueError, match='missing Math questions'):
        check_completeness(_details(), _totals(math=MIN_MATH_QUESTIONS - 1))


def test_partial_rw_still_rejected_when_math_is_absent():
    with pytest.raises(ValueError, match='missing RW questions'):
        check_completeness(
            _details(is_math_found=False, math_answered=0),
            _totals(rw=MIN_RW_QUESTIONS - 1, math=0))


# --- answered-question floor --------------------------------------------------

def test_blank_test_is_rejected():
    with pytest.raises(ValueError, match='insufficient questions answered'):
        check_completeness(
            _details(rw_answered=MIN_ANSWERED - 1, math_answered=MIN_ANSWERED - 1),
            _totals())


def test_one_section_answered_is_enough():
    check_completeness(
        _details(rw_answered=0, math_answered=44, is_rw_found=False), _totals(rw=0))


# --- check_answer_key ---------------------------------------------------------

def _answers(correct):
    """A full sat7 answer set, overridden at the given (sub, mod, q) keys."""
    sizes = {'rw': 27, 'math': 22}
    out = {}
    for sub, n in sizes.items():
        out[sub] = {}
        for mod in ('1', '2'):
            out[sub][mod] = {
                str(q): {'correct_answer': correct.get((sub, mod, str(q)), None),
                         'student_answer': 'A', 'is_correct': True}
                for q in range(1, n + 1)
            }
    return out


def _score_data(answers, is_rw_found=True, is_math_found=True):
    return {
        'test_code': 'sat7',
        'is_rw_hard': False,
        'is_math_hard': False,
        'is_rw_found': is_rw_found,
        'is_math_found': is_math_found,
        'answer_key_mismatches': [],
        'missing_data': [],
        'answers': answers,
    }


def _correct_sat7():
    """Read the stored sat7 key back out of check_answer_key by round-tripping
    a placeholder set and taking the reported 'previous_key' for every row."""
    data = _score_data(_answers({}))
    for sub in data['answers']:
        for mod in data['answers'][sub]:
            for q in data['answers'][sub][mod]:
                data['answers'][sub][mod][q]['correct_answer'] = '\x00'
    check_answer_key(data)
    return {(m['sub'], m['mod'], m['q']): m['previous_key']
            for m in data['answer_key_mismatches']}


def test_matching_key_reports_nothing():
    data = _score_data(_answers(_correct_sat7()))
    check_answer_key(data)
    assert data['answer_key_mismatches'] == []
    assert data['missing_data'] == []


def test_absent_section_is_not_reported_as_missing_data():
    """A Math-only export must not report all 54 RW rows as missing."""
    answers = _answers(_correct_sat7())
    for mod in ('1', '2'):
        for q in answers['rw'][mod]:
            answers['rw'][mod][q]['correct_answer'] = 'not found'
    data = _score_data(answers, is_rw_found=False)
    check_answer_key(data)
    assert data['missing_data'] == []
    assert data['answer_key_mismatches'] == []


def test_present_section_still_reports_missing_rows():
    answers = _answers(_correct_sat7())
    answers['math']['1']['3']['correct_answer'] = 'not found'
    data = _score_data(answers)
    check_answer_key(data)
    assert data['missing_data'] == [{'sub': 'math', 'mod': '1', 'q': '3'}]


def test_changed_key_is_reported_as_a_mismatch():
    answers = _answers(_correct_sat7())
    answers['math']['1']['1']['correct_answer'] = 'ZZZ'
    data = _score_data(answers)
    check_answer_key(data)
    assert len(data['answer_key_mismatches']) == 1
    assert data['answer_key_mismatches'][0]['new_key'] == 'ZZZ'


# --- student name extraction --------------------------------------------------

@pytest.mark.parametrize('text, expected', [
    ('Name: Ada Lovelace\nThis practice score report', 'Ada Lovelace'),
    ('Name:Ada Lovelace\nThis practice score report', 'Ada Lovelace'),
    ('Name:  Ada Lovelace  \nrest', 'Ada Lovelace'),
    ('Your Practice\nName: Ada Lovelace\nrest', 'Ada Lovelace'),
    ('Name: Ada Lovelace', 'Ada Lovelace'),                 # no trailing newline
    ('Name: AdaLovelace\nrest', 'Ada Lovelace'),            # space lost in the PDF
    ('Name: LilaLovelace\nrest', 'Lila Lovelace'),          # capital repeats the initial
    ('Name: Ada van der Lovelace\nrest', 'Ada van der Lovelace'),
    ('Name: Ada\nrest', 'Ada'),                     # single name, no capital to split
])
def test_parse_student_name(text, expected):
    assert parse_student_name(text) == expected


def test_parse_student_name_returns_none_without_the_label():
    """Regression: guarding on the derived offset instead of the label index
    made this return a slice of unrelated page text as the student's name."""
    assert parse_student_name('This practice score report is provided by College') is None


def test_parse_student_name_returns_none_when_blank():
    assert parse_student_name('Name: \nrest') is None


# --- repeated table header must not leak into a row's answer key ---------------

class _FakePage:
    height = 792

    def __init__(self, words):
        self._words = words

    def extract_text(self):
        return 'My Tests / SAT Practice 8 - July 11, 2026'

    def extract_words(self):
        return [dict(text=t, x0=x, top=top) for t, x, top in self._words]


def test_repeated_header_words_do_not_leak_into_first_row_answer(monkeypatch):
    from sat_score_reader import details

    header = [('Question', 24, 12.0), ('Section', 96, 12.7), ('Correct', 192, 12.7),
              ('Your', 281, 12.7), ('Actions', 362, 12.7), ('', 576, 12.0),
              ('Answer', 192, 30.7), ('Answer', 281, 30.7)]
    def row(n, top, answer):
        return [(str(n), 24, top), ('Math', 96, top), (answer + ';', 281, top),
                ('Correct', 294, top), ('Review', 380, top), (answer, 192, top)]

    # The header repeats at the top of every page, so row 2 -- the first on page
    # two -- is the one whose band reaches back up into it.
    class _Pdf:
        pages = [_FakePage(header + row(1, 700, 'C')), _FakePage(header + row(2, 69, 'D'))]

    monkeypatch.setattr(details.pdfplumber, 'open', lambda path: _Pdf())
    monkeypatch.setattr(details, 'check_completeness', lambda *a: None)
    data = details.get_student_answers('unused.pdf')
    assert data['answers']['math']['1']['2']['correct_answer'] == 'D'
