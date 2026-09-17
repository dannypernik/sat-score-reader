"""Parsing of the score-report PDF: student name, section scores, total."""

import datetime
import logging
import re

import pdfplumber


def parse_student_name(text):
  """Pull the student name off a score report page, or None if absent.

  Returns None when the page carries no 'Name:' label -- the caller keeps
  looking on later pages. Guarding on the label's index rather than on the
  derived offset matters: str.find returns -1, so an offset-based test passes
  for a page without the label and yields a slice of unrelated text as a name.
  """
  label_at = text.find('Name:')
  if label_at == -1:
    return None

  name_start = label_at + len('Name:')
  # Some exports render 'Name: Ada', others 'Name:Ada'.
  if text[name_start:name_start + 1] == ' ':
    name_start += 1
  name_end = text.find('\n', name_start)
  if name_end == -1:
    name_end = len(text)

  student_name = text[name_start:name_end].strip()
  if not student_name:
    return None

  # A name that lost its space in the PDF ('AdaLovelace') splits at the first
  # interior capital. Insert at that index rather than replacing the character,
  # which would also split every later repeat of it ('LilaLovelace').
  if ' ' not in student_name:
    for i, char in enumerate(student_name[1:], 1):
      if char.isupper():
        student_name = student_name[:i] + ' ' + student_name[i:]
        break
  return student_name


def get_data_from_score_report(data, pdf_path):
  pdf = pdfplumber.open(pdf_path)
  pages = pdf.pages

  data['student_name'] = None
  data['rw_score'] = None
  data['math_score'] = None
  data['total_score'] = None

  try:
    for page in pages:
      text = page.extract_text()
      # print(text)
      # Extract student name
      if not data['student_name']:
        data['student_name'] = parse_student_name(text)

      # Extract total score and remaining values
      scores = re.findall(r'(\s\d{3}\s|\s\d{4}\s)', text)
      scores = [int(score) for score in scores if 160 <= int(score) <= 1600]
      if scores:
        data['total_score'] = max(scores)
        remaining_values = [int(value) for value in scores if value != data['total_score']]
        if len(remaining_values) >= 2:
          for i in range(len(remaining_values) - 1):
            for j in range(i+1, len(remaining_values)):
              if remaining_values[i] + remaining_values[j] == data['total_score']:
                data['rw_score'] = remaining_values[i]
                data['math_score'] = remaining_values[j]
                break
            if not data['rw_score']:
              break

      # Find lines that start with SAT or PSAT
      sat_lines = [line for line in text.split('\n') if line.startswith('SAT') or line.startswith('PSAT')]
      valid_sat_lines = [line for line in sat_lines if line.endswith(tuple(str(year) for year in range(2020, 2100)))]
      sat_line = valid_sat_lines[0] if valid_sat_lines else None
      title_line = sat_line.rstrip() if sat_line else None # ensures no trailing whitespace
      if title_line:
        test_type = sat_line[0:sat_line.find('SAT') + 3]
      test_number_start = sat_line.find('Practice') + 9
      test_number_end = sat_line.find(' ', test_number_start)
      test_number = sat_line[test_number_start:test_number_end]
      test_code = test_type.lower() + test_number

      date_start = sat_line.find(' ', test_number_end) + 1
      # Strip spaces on both sides so 'February 28, 2025' and any variant
      # spacing pdfplumber reports for the same line both parse.
      date_str_condensed = sat_line[date_start:].replace(' ', '')
      date = datetime.datetime.strptime(date_str_condensed, '%B%d,%Y').strftime('%Y.%m.%d')
    if date != data['date'] or test_code != data['test_code']:
      raise ValueError(f'Score report error: date or test code mismatch. {date} != {data["date"]} or {test_code} != {data["test_code"]}')
    if not data['rw_score'] or not data['math_score']:
      raise ValueError('Score report error: rw_score or math_score not found')
    return data
  except Exception as e:
    logging.error(f'Error reading score report: {e}')
    raise
