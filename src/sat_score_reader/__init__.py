"""Read College Board SAT/PSAT practice-test PDFs into structured scores.

Two PDFs per sitting: a *details* export listing every question with its
correct answer, the student's response, and a Correct/Incorrect/Omitted
result; and a *report* giving the student's name and scaled scores.

    from sat_score_reader import get_all_data
    data = get_all_data(report_path, details_path)

Correctness always comes from the result word in the details PDF, never from
comparing a response against the stored key -- grid-ins accept several forms
of the same value and the keys hold only the first one CB lists.
"""

import logging

from .answer_keys import ANSWER_KEYS, MODULE_DIFFICULTY
from .checks import check_answer_key, get_mod_difficulty, print_answer_key
from .details import (
    MIN_ANSWERED,
    MIN_MATH_QUESTIONS,
    MIN_RW_QUESTIONS,
    check_completeness,
    get_student_answers,
)
from .report import get_data_from_score_report, parse_student_name

__version__ = '1.1.1'

__all__ = [
    'ANSWER_KEYS',
    'MIN_ANSWERED',
    'MIN_MATH_QUESTIONS',
    'MIN_RW_QUESTIONS',
    'MODULE_DIFFICULTY',
    'check_answer_key',
    'check_completeness',
    'get_all_data',
    'get_data_from_score_report',
    'get_mod_difficulty',
    'get_student_answers',
    'parse_student_name',
    'print_answer_key',
]


def get_all_data(report_path, details_path):
  """Parse a details/report pair into one score dict.

  The two files are accepted in either order: whichever one parses as a
  details export is used as such, and the other is read as the report.
  """
  data = get_student_answers(details_path)
  if data == "invalid":
    data = get_student_answers(report_path)
    report_path, details_path = details_path, report_path
    if data == "invalid":
      raise FileNotFoundError('Score Details PDF does not match expected format')
  data = get_data_from_score_report(data, report_path)
  data = get_mod_difficulty(data)
  data = check_answer_key(data)
  return data
