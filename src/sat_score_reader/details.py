"""Parsing of the score-details PDF: every question, its key, and the response."""

import datetime
import re
from collections import Counter

import pdfplumber


# A details export must be substantially complete for the section(s) it covers.
# Of 54 Reading and Writing rows and 44 Math rows, allow a handful to be lost to
# PDF quirks before refusing to build a report on what's left.
MIN_RW_QUESTIONS = 44
MIN_MATH_QUESTIONS = 34
MIN_ANSWERED = 5


def check_completeness(score_details_data, subject_totals):
  """Raise ValueError if the parsed details are too incomplete to report on.

  An export may cover Reading and Writing only, or Math only -- students
  routinely submit one section at a time -- but not neither. A section that IS
  present has to be substantially complete: without that check a section whose
  rows all failed to parse looks identical to one the export never contained,
  and would silently yield a report missing most of its questions.
  """
  is_rw_found = score_details_data['is_rw_found']
  is_math_found = score_details_data['is_math_found']

  if not is_rw_found and not is_math_found:
    raise ValueError('Error reading score details: no questions found')
  if is_rw_found and subject_totals['rw'] < MIN_RW_QUESTIONS:
    raise ValueError('Error reading score details: missing RW questions')
  if is_math_found and subject_totals['math'] < MIN_MATH_QUESTIONS:
    raise ValueError('Error reading score details: missing Math questions')
  if (score_details_data['rw_questions_answered'] < MIN_ANSWERED
      and score_details_data['math_questions_answered'] < MIN_ANSWERED):
    raise ValueError('Error reading score details: insufficient questions answered')


def get_student_answers(score_details_file_path):
  """
  Extract student answers from a SAT practice test score details PDF.

  Rows are reconstructed from word bounding boxes rather than pdfplumber's
  line-clustered text. Wrapped Domain cells (e.g. "Problem-Solving and Data
  Analysis") and multi-line grid-in answer keys (e.g. accepted answers stacked
  across lines) otherwise land on the same y-coordinate as neighboring rows,
  which scrambles pdfplumber's text-line output and silently drops or
  corrupts data — including across a PDF page break.
  """
  total_questions = {
    'rw': {'questions': 27},
    'math': {'questions': 22}
  }
  pdf = pdfplumber.open(score_details_file_path)
  pages = pdf.pages

  score_details_data = {
      'test_code': None,
      'test_display_name': None,
      'date': None,
      'is_rw_found': False,
      'is_math_found': False,
      'rw_score': 100,
      'math_score': 100,
      'is_rw_hard': None,
      'is_math_hard': None,
      'has_omits': False,
      'answer_key_mismatches': [],
      'missing_data': [],
      'answers': {
        'rw': {
          '1': {},
          '2': {}
        },
        'math': {
          '1': {},
          '2': {}
        },
      },
  }

  # Test date/code come from the "My Tests / <Type> <N> - <Date>" breadcrumb,
  # which is plain unwrapped text on the first page.
  date = None
  test_number = None
  first_page_text = pages[0].extract_text() or ''
  for line in first_page_text.split('\n'):
    if line.find('My Tests') != -1:
      trimmed_line = line.rstrip()
      date_start = trimmed_line.find(' - ') + 3
      date_str = trimmed_line[date_start:]
      date = datetime.datetime.strptime(date_str, '%B %d, %Y').strftime('%Y.%m.%d')
      score_details_data['date'] = date

      test_type_start = line.find('My Tests') + 11
      sep = {'/', ' '}
      test_type_end = next((i for i, ch in enumerate(line[test_type_start:]) if ch in sep), None) + test_type_start
      test_type = line[test_type_start:test_type_end]
      test_number_end = date_start - 3
      test_number_start = line.rfind(" ", 0, test_number_end) + 1

      test_number = line[test_number_start:test_number_end]
      score_details_data['test_code'] = test_type.lower() + test_number
      score_details_data['test_display_name'] = f'{test_type.upper()} {test_number}'
      break

  # Gather every word on every page, offsetting vertical position by each
  # page's actual height so coordinates stay continuous across a page break
  # (a row split across pages must bucket next to its neighbors, not across
  # an arbitrary gap).
  noise_re = re.compile(r'^(https?://|MyPractice)')
  # Words that occur only in the repeated table chrome -- the column-header
  # line and the "All Questions | Reading and Writing | Math" filter row. No
  # Domain or answer cell contains any of them, so they identify those lines
  # unambiguously. Their siblings ('All', 'Correct', 'Answer', and a bare
  # 'Math' that would relabel the section) are words that do occur in real
  # rows, which is why the whole line has to go rather than the marker word.
  table_chrome = {'Section', 'Actions', 'Questions'}
  # Icon-font glyphs (the header's sort arrows) live in the Private Use Area
  # and carry no text. They don't reliably share a line with the header words,
  # so drop them per-word rather than per-line.
  icon_re = re.compile(r'^[\ue000-\uf8ff]+$')
  all_words = []
  cum_offset = 0
  for p in pages:
    words = p.extract_words()
    # The running header/timestamp and footer/page-number are each one text
    # line; drop every word on that line, not just the one matching noise_re,
    # since sibling words on the same line don't themselves start with
    # 'http'/'MyPractice' and would otherwise leak into a row's answer cell.
    noise_tops = {round(w['top'], 1) for w in words
                  if noise_re.match(w['text']) or w['text'] in table_chrome}
    for w in words:
      if round(w['top'], 1) in noise_tops or icon_re.match(w['text']):
        continue
      all_words.append({
        'text': w['text'],
        'x0': w['x0'],
        'top': w['top'] + cum_offset,
      })
    cum_offset += p.height

  # Locate the Question-number column: it's the x0 where 1-99 digit words
  # cluster far more densely than anywhere else (grid-in answers scatter
  # digits elsewhere on the row, but never at this consistent left edge).
  digit_x_counts = Counter()
  for w in all_words:
    if w['text'].isdigit() and 1 <= int(w['text']) <= 99:
      digit_x_counts[round(w['x0'] / 3) * 3] += 1
  question_x = max(digit_x_counts, key=digit_x_counts.get) if digit_x_counts else None

  anchors = sorted(
    (w for w in all_words
     if w['text'].isdigit() and 1 <= int(w['text']) <= 99 and question_x is not None
     and abs(w['x0'] - question_x) <= 6),
    key=lambda w: w['top']
  )

  # "Review" is an exact, unambiguous marker for the Actions column; anything
  # at or past its x0 is the (score-irrelevant) Domain column.
  review_xs = [w['x0'] for w in all_words if w['text'] == 'Review']
  review_x = sum(review_xs) / len(review_xs) if review_xs else float('inf')

  section_words = {'Reading', 'and', 'Writing', 'Math'}

  # A row's own cells (response value, result word) don't reliably render on
  # the same sub-line as its question-number anchor — a wrapped Section or
  # Domain cell can push them a line above or below it. But every row
  # contributes exactly one result word (Correct/Incorrect/Omitted) and, for
  # non-omitted rows, exactly one response value, and rows are never
  # reordered — so matching these word-streams to anchors by document order
  # is robust where nearest-anchor-by-position is not.
  first_top = anchors[0]['top'] if anchors else 0

  # Locate the Section column the same way as the Question column: its label
  # recurs once per row at one x0, so it dominates every other placement of
  # those words. Matching the bare word anywhere in a row's band instead is
  # wrong twice over -- each page repeats a filter row ("All Questions |
  # Reading and Writing | Math") that the first row's band can swallow, and
  # the Domain column carries "Advanced Math". Either one relabels the export
  # from its first row onward, silently dropping a whole section.
  section_x_counts = Counter()
  for w in all_words:
    if w['text'] in ('Reading', 'Math') and w['top'] >= first_top - 20:
      section_x_counts[round(w['x0'] / 3) * 3] += 1
  section_x = max(section_x_counts, key=section_x_counts.get) if section_x_counts else None
  results_stream = sorted(
    (w for w in all_words
     if w['text'] in ('Correct', 'Incorrect', 'Omitted')
     and w['x0'] < review_x - 5 and w['top'] >= first_top - 10),
    key=lambda w: w['top']
  )
  responses_stream = sorted(
    (w for w in all_words
     if w['text'].endswith(';') and w['x0'] < review_x - 5 and w['top'] >= first_top - 10),
    key=lambda w: w['top']
  )

  subject = 'rw'
  rw_mod_num = '1'
  m_mod_num = '1'
  subject_totals = {'rw': 0, 'math': 0}
  # Rows *seen* per subject, counted before the completeness gate below. A
  # section the PDF never contained and a section whose rows all failed to
  # parse both leave subject_totals at 0, but only the first is a legitimate
  # single-subject export -- the second must still be rejected. Every row
  # carries its own Section-column label, so anchor attribution separates them.
  subject_rows = {'rw': 0, 'math': 0}
  response_idx = 0

  for i, anchor in enumerate(anchors):
    number = anchor['text']
    prev_top = anchors[i - 1]['top'] if i > 0 else anchor['top'] - 40
    next_top = anchors[i + 1]['top'] if i + 1 < len(anchors) else anchor['top'] + 40
    row_top = (prev_top + anchor['top']) / 2
    row_bottom = (anchor['top'] + next_top) / 2
    row_words = [w for w in all_words if row_top <= w['top'] < row_bottom]

    # Read the subject off this row's own Section cell; carry the previous
    # row's forward when the cell doesn't render (merged/wrapped), which also
    # keeps the reader independent of the order the sections appear in.
    row_sections = {w['text'] for w in row_words
                    if section_x is not None and abs(w['x0'] - section_x) <= 6
                    and w['text'] in ('Reading', 'Math')}
    if 'Math' in row_sections:
      subject = 'math'
    elif 'Reading' in row_sections:
      subject = 'rw'

    result = results_stream[i]['text'] if i < len(results_stream) else None

    answer_parts = [
      w for w in row_words
      if w is not anchor and w['x0'] < review_x - 5
      and w['text'] not in section_words
      and w['text'] not in ('Correct', 'Incorrect', 'Omitted')
      and not w['text'].endswith(';')
    ]
    answer_parts.sort(key=lambda w: w['top'])
    # A grid-in cell lists every accepted form of the answer (e.g. "11/4, 2.75").
    # Keep only College Board's first listed form: correctness comes from the
    # Correct/Incorrect/Omitted word, never from matching the student's response
    # against this key, so the alternate forms are unused — and storing them
    # would make every multi-form grid-in look like an answer-key mismatch.
    correct_answer = ''.join(w['text'] for w in answer_parts).split(',')[0] or None

    if result == 'Omitted':
      response = '-'
      score_details_data['has_omits'] = True
    elif result is not None:
      response = responses_stream[response_idx]['text'].rstrip(';') if response_idx < len(responses_stream) else None
      response_idx += 1
    else:
      # No result word means this row's data wasn't captured (e.g. the PDF
      # export was truncated mid-row) — don't guess at correctness.
      response = None

    is_correct = result == 'Correct'

    if score_details_data['answers']['math']['1'].get(number):
      m_mod_num = '2'

    if score_details_data['answers']['rw']['1'].get(number):
      rw_mod_num = '2'

    if subject:
      subject_rows[subject] += 1

    if subject and number and correct_answer and response and result:
      subject_totals[subject] += 1

      if subject == 'rw':
        module = rw_mod_num
      elif subject == 'math':
        module = m_mod_num

      score_details_data['answers'][subject][module][number] = {
        'correct_answer': correct_answer,
        'student_answer': response,
        'is_correct': is_correct
      }

  rw_questions_answered = 0
  math_questions_answered = 0

  for sub in ['rw', 'math']:
    for mod in range(1, 3):
      for q in range(1, total_questions[sub]['questions'] + 1):
        if score_details_data['answers'][sub][str(mod)].get(str(q)) is None:
          score_details_data['answers'][sub][str(mod)][str(q)] = {
            'correct_answer': 'not found',
            'student_answer': 'not found',
            'is_correct': False
          }
        elif sub == 'rw' and score_details_data['answers'][sub][str(mod)][str(q)][
          'student_answer'] != '-':
          rw_questions_answered += 1
        elif sub == 'math' and score_details_data['answers'][sub][str(mod)][str(q)][
          'student_answer'] != '-':
          math_questions_answered += 1

  score_details_data['is_rw_found'] = subject_rows['rw'] > 0
  score_details_data['is_math_found'] = subject_rows['math'] > 0
  score_details_data['rw_questions_answered'] = rw_questions_answered
  score_details_data['math_questions_answered'] = math_questions_answered

  # pp.pprint(score_details_data)

  if date is None:
    return "invalid"
  elif int(test_number) > 11:
        raise ValueError('Test unavailable')

  check_completeness(score_details_data, subject_totals)

  return score_details_data
