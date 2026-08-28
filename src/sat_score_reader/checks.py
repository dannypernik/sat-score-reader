"""Deriving module difficulty and verifying a parse against the stored keys."""

import pprint

from .answer_keys import ANSWER_KEYS, MODULE_DIFFICULTY

pp = pprint.PrettyPrinter(indent=2, width=100)


def get_mod_difficulty(score_details_data):
  easy_rw_diff_answer = MODULE_DIFFICULTY[score_details_data['test_code']]['rw']['easy_answer']
  hard_rw_diff_answer = MODULE_DIFFICULTY[score_details_data['test_code']]['rw']['hard_answer']
  pdf_rw_diff_answer = score_details_data['answers']['rw']['2'][MODULE_DIFFICULTY[score_details_data['test_code']]['rw']['diff_question']]['correct_answer']
  if hard_rw_diff_answer == pdf_rw_diff_answer:
    score_details_data['is_rw_hard'] = True
  elif easy_rw_diff_answer == pdf_rw_diff_answer:
    score_details_data['is_rw_hard'] = False
  else:
    score_details_data['is_rw_hard'] = None

  easy_m_diff_answer = MODULE_DIFFICULTY[score_details_data['test_code']]['m']['easy_answer']
  hard_m_diff_answer = MODULE_DIFFICULTY[score_details_data['test_code']]['m']['hard_answer']
  pdf_m_diff_answer = score_details_data['answers']['math']['2'][MODULE_DIFFICULTY[score_details_data['test_code']]['m']['diff_question']]['correct_answer']
  if hard_m_diff_answer == pdf_m_diff_answer:
    score_details_data['is_math_hard'] = True
  elif easy_m_diff_answer == pdf_m_diff_answer:
    score_details_data['is_math_hard'] = False
  else:
    score_details_data['is_math_hard'] = None

  return score_details_data


def print_answer_key(score_details_data):
  answer_key = {
    'test_code': score_details_data['test_code'],
    'is_rw_hard': score_details_data['is_rw_hard'],
    'is_math_hard': score_details_data['is_math_hard'],
    'rw': {
      '1': {},
      '2': {}
    },
    'math': {
      '1': {},
      '2': {}
    }
  }
  for sub in score_details_data['answers']:
    for mod in score_details_data['answers'][sub]:
      for q in score_details_data['answers'][sub][mod]:
        correct_answer = score_details_data['answers'][sub][mod][q]['correct_answer'].rstrip(',')
        answer_key[sub][mod][q] = correct_answer
  pp.pprint(answer_key)


def check_answer_key(score_details_data):
  for sub in score_details_data['answers']:
    for mod in score_details_data['answers'][sub]:
      key_mod = mod
      if mod == '2' and ((sub == 'rw' and score_details_data['is_rw_hard']) or (sub == 'math' and score_details_data['is_math_hard'])):
        key_mod = '3'
      # A subject the export never covered is legitimately absent, not missing
      # data -- reporting all 54 of its rows would bury any real discrepancy.
      if not score_details_data[f'is_{sub}_found']:
        continue
      for q in score_details_data['answers'][sub][mod]:
        if score_details_data['answers'][sub][mod][q]['correct_answer'] == 'not found':
          score_details_data['missing_data'].append({
            'sub': sub,
            'mod': mod,
            'q': q
          })
        elif score_details_data['answers'][sub][mod][q]['correct_answer'] != ANSWER_KEYS[score_details_data['test_code']][sub][key_mod][q]:
          score_details_data['answer_key_mismatches'].append({
            'sub': sub,
            'mod': mod,
            'q': q,
            'previous_key': ANSWER_KEYS[score_details_data['test_code']][sub][key_mod][q],
            'new_key': score_details_data['answers'][sub][mod][q]['correct_answer']
          })

  return score_details_data
