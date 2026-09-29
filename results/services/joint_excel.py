"""
Excel ya Halmashauri kwa joint exam — faili MOJA la shule zote (Serikali +
Binafsi, safu ya UMILIKI), kwa format ya mafaili ya Halmashauri:

  DIVISION          — muhtasari wa madaraja + nafasi kiwilaya
  GRADE             — gredi ya wastani wa wanafunzi (A–F) kwa kila shule
  LIST OF SUBJECTS  — ranking ya masomo (wilaya nzima)
  <somo>            — sheet moja kwa kila somo: kila shule A–F, PASS, %, GPA
"""
from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .joint_analysis import DIVISIONS, GRADES, analyse_joint_exam

FORM_SW = {1: 'KIDATO CHA KWANZA', 2: 'KIDATO CHA PILI', 3: 'KIDATO CHA TATU',
           4: 'KIDATO CHA NNE', 5: 'KIDATO CHA TANO', 6: 'KIDATO CHA SITA'}
MONTH_SW = ['JANUARI', 'FEBRUARI', 'MACHI', 'APRILI', 'MEI', 'JUNI', 'JULAI',
            'AGOSTI', 'SEPTEMBA', 'OKTOBA', 'NOVEMBA', 'DESEMBA']

THIN = Side(style='thin', color='000000')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center')
HEAD_FILL = PatternFill('solid', fgColor='D9E1F2')
TOTAL_FILL = PatternFill('solid', fgColor='FFF2CC')
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=12)


def _num(v, digits=2):
    return '-' if v is None else round(v, digits)


def _titles(ws, joint, heading, ncols):
    when = ''
    if joint.date:
        when = f'{MONTH_SW[joint.date.month - 1]} {joint.date.year}'
    else:
        when = str(joint.year)
    lines = [
        'OFISI YA WAZIRI MKUU - TAMISEMI',
        f'HALMASHAURI YA WILAYA YA {joint.district.upper()}',
        f'MUHTASARI WA MATOKEO YA {joint.name.upper()}, '
        f'{FORM_SW.get(joint.form, f"KIDATO {joint.form}")} {when}',
        '',
        heading,
    ]
    for i, text in enumerate(lines, 1):
        if not text:
            continue
        ws.cell(row=i, column=1, value=text).font = TITLE
        ws.cell(row=i, column=1).alignment = CENTER
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=ncols)


def _head(ws, row, col, text, rowspan=1, colspan=1):
    c = ws.cell(row=row, column=col, value=text)
    if rowspan > 1 or colspan > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row + rowspan - 1, end_column=col + colspan - 1)
    for r in range(row, row + rowspan):
        for cc in range(col, col + colspan):
            cell = ws.cell(row=r, column=cc)
            cell.font = BOLD
            cell.alignment = CENTER
            cell.fill = HEAD_FILL
            cell.border = BORDER


def _write_row(ws, row, values, total=False, left_cols=()):
    for i, v in enumerate(values, 1):
        c = ws.cell(row=row, column=i, value=v)
        c.border = BORDER
        c.alignment = LEFT if i in left_cols else CENTER
        if total:
            c.font = BOLD
            c.fill = TOTAL_FILL


def _widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def _mft(b, order='MFT'):
    return [b[k] for k in order]


# ── DIVISION ──

def _division_sheet(wb, joint, data):
    ws = wb.active
    ws.title = 'DIVISION'
    ncols = 44
    _titles(ws, joint, 'DIVISION PERFORMANCE SUMMARY', ncols)
    r = 6
    for col, text in enumerate(['S/N', 'HALMASHAURI', 'KATA', 'UMILIKI', 'JINA LA SHULE'], 1):
        _head(ws, r, col, text, rowspan=3)
    _head(ws, r, 6, 'WALIOSAJILIWA', rowspan=2, colspan=3)
    _head(ws, r, 9, 'WALIOFANYA', rowspan=2, colspan=3)
    _head(ws, r, 12, 'WASIOFANYA', rowspan=2, colspan=3)
    _head(ws, r, 15, 'DARAJA/DIVISION', colspan=29)
    _head(ws, r, 44, 'NAFASI KIWILAYA', rowspan=3)
    col = 15
    for label in DIVISIONS + ['I-III']:
        _head(ws, r + 1, col, label, colspan=3)
        col += 3
    _head(ws, r + 1, col, '%', rowspan=2); col += 1                 # % I-III
    _head(ws, r + 1, col, 'I - IV', colspan=3); col += 3
    _head(ws, r + 1, col, '%', rowspan=2); col += 1
    _head(ws, r + 1, col, 'IV-0', colspan=3); col += 3
    _head(ws, r + 1, col, '%IV-0', rowspan=2); col += 1
    _head(ws, r + 1, col, 'PASS', rowspan=2); col += 1
    _head(ws, r + 1, col, 'GPA', rowspan=2); col += 1
    # WAV/WAS/JML chini ya kila kundi la 3
    triple_starts = [6, 9, 12, 15, 18, 21, 24, 27, 30, 34, 38]
    for start in triple_starts:
        for off, t in enumerate(['WAV', 'WAS', 'JML']):
            _head(ws, r + 2, start + off, t)

    row = r + 3
    district = f'{joint.district.upper()} DC'
    for i, s in enumerate(data['schools'], 1):
        d = s['divisions']
        _write_row(ws, row, [
            i, district, s['ward'].upper(), s['ownership'].upper(),
            s['school'].name.upper() if s['school'] else '',
            *_mft(s['registered']), *_mft(s['sat']), *_mft(s['absent']),
            *[v for div in DIVISIONS for v in _mft(d[div])],
            *_mft(s['i_iii']), _num(s['i_iii_pct']),
            *_mft(s['i_iv']), _num(s['i_iv_pct']),
            *_mft(s['iv_0']), _num(s['iv_0_pct']),
            s['pass'], _num(s['gpa']), s['rank'] or '-',
        ], left_cols=(2, 3, 4, 5))
        row += 1
    t = data['totals']
    _write_row(ws, row, [
        'TOTAL', '', '', '', f'{len(data["schools"])} SCHOOLS',
        *_mft(t['registered']), *_mft(t['sat']), *_mft(t['absent']),
        *[v for div in DIVISIONS for v in _mft(t['divisions'][div])],
        *_mft(t['i_iii']), _num(t['i_iii_pct']),
        *_mft(t['i_iv']), _num(t['i_iv_pct']),
        *_mft(t['iv_0']), _num(t['iv_0_pct']),
        t['pass'], _num(t['gpa']), '',
    ], total=True)
    _widths(ws, {1: 5, 2: 12, 3: 14, 4: 10, 5: 38})
    for c in range(6, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 6
    ws.freeze_panes = 'F9'


# ── GRADE ──

def _grade_sheet(wb, joint, data):
    ws = wb.create_sheet('GRADE')
    ncols = 28
    _titles(ws, joint, 'GRADE PERFORMANCE SUMMARY', ncols)
    r = 6
    for col, text in enumerate(['SN', 'WARD', 'UMILIKI', 'SCHOOL NAME'], 1):
        _head(ws, r, col, text, rowspan=2)
    col = 5
    for label in ['SAT'] + GRADES + ['PASS(A-D)']:
        _head(ws, r, col, label, colspan=3)
        for off, t in enumerate('FMT'):
            _head(ws, r + 1, col + off, t)
        col += 3
    _head(ws, r, col, '%', rowspan=2)
    _head(ws, r, col + 1, 'GPA', rowspan=2)
    _head(ws, r, col + 2, 'NAFASI', rowspan=2)

    rows = sorted(data['schools'], key=lambda s: (s['grade_rank'] is None, s['grade_rank'] or 0))
    row = r + 2
    for i, s in enumerate(rows, 1):
        g = s['grade']
        _write_row(ws, row, [
            i, s['ward'].upper(), s['ownership'].upper(),
            s['school'].name.upper() if s['school'] else '',
            *_mft(g['sat'], 'FMT'),
            *[v for gr in GRADES for v in _mft(g['grades'][gr], 'FMT')],
            *_mft(g['pass'], 'FMT'), _num(g['pass_pct']), _num(g['gpa']),
            s['grade_rank'] or '-',
        ], left_cols=(2, 3, 4))
        row += 1
    g = data['totals']['grade']
    _write_row(ws, row, [
        '', 'TOTAL', '', '', *_mft(g['sat'], 'FMT'),
        *[v for gr in GRADES for v in _mft(g['grades'][gr], 'FMT')],
        *_mft(g['pass'], 'FMT'), _num(g['pass_pct']), _num(g['gpa']), '',
    ], total=True)
    _widths(ws, {1: 5, 2: 14, 3: 10, 4: 38})
    for c in range(5, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 6
    ws.freeze_panes = 'E8'


# ── MASOMO ──

def _subject_header(ws, r, first_cols):
    for col, text in enumerate(first_cols, 1):
        _head(ws, r, col, text, rowspan=2)
    col = len(first_cols) + 1
    for label in ['REGISTERED'] + GRADES + ['PASS (A-D)']:
        _head(ws, r, col, label, colspan=3)
        for off, t in enumerate('MFT'):
            _head(ws, r + 1, col + off, t)
        col += 3
    _head(ws, r, col, '%', rowspan=2)
    _head(ws, r, col + 1, 'GPA', rowspan=2)
    _head(ws, r, col + 2, 'NAFASI', rowspan=2)
    return col + 2


def _grade_cells(b):
    return [
        *_mft(b['sat']),
        *[v for gr in GRADES for v in _mft(b['grades'][gr])],
        *_mft(b['pass']), _num(b['pass_pct']), _num(b['gpa']),
    ]


def _subjects_list_sheet(wb, joint, data):
    ws = wb.create_sheet('LIST OF SUBJECTS')
    ncols = 2 + 21 + 3
    _titles(ws, joint, 'SUBJECT PERFORMANCE RANKING', ncols)
    _subject_header(ws, 6, ['S/N', 'SUBJECT NAME'])
    row = 8
    for i, s in enumerate(data['subjects'], 1):
        _write_row(ws, row, [i, s['name'].upper(), *_grade_cells(s), s['rank'] or '-'],
                   left_cols=(2,))
        row += 1
    _widths(ws, {1: 5, 2: 34})
    for c in range(3, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 6
    ws.freeze_panes = 'C8'


def _sheet_name(name, used):
    base = re.sub(r'[\[\]\*\?/\\:]', ' ', name.upper()).strip()[:28] or 'SUBJECT'
    title, n = base, 2
    while title in used or title in ('DIVISION', 'GRADE', 'LIST OF SUBJECTS'):
        title = f'{base[:26]} {n}'
        n += 1
    used.add(title)
    return title


def _subject_sheets(wb, joint, data):
    used = set()
    for s in sorted(data['subjects'], key=lambda x: x['name']):
        ws = wb.create_sheet(_sheet_name(s['name'], used))
        ncols = 4 + 21 + 3
        _titles(ws, joint, f'{s["name"].upper()} — SUBJECT GRADE PERFORMANCE ANALYSIS', ncols)
        _subject_header(ws, 6, ['S/N', 'NAME OF THE SCHOOL', 'WARD', 'UMILIKI'])
        row = 8
        for i, r in enumerate(s['rows'], 1):
            _write_row(ws, row, [
                i, r['school'].name.upper() if r['school'] else '',
                r['ward'].upper(), r['ownership'].upper(),
                *_grade_cells(r), r['rank'] or '-',
            ], left_cols=(2, 3, 4))
            row += 1
        _write_row(ws, row, ['', 'TOTAL', '', '', *_grade_cells(s), ''], total=True)
        _widths(ws, {1: 5, 2: 38, 3: 14, 4: 10})
        for c in range(5, ncols + 1):
            ws.column_dimensions[get_column_letter(c)].width = 6
        ws.freeze_panes = 'E8'


def build_joint_workbook(joint) -> bytes:
    data = analyse_joint_exam(joint)
    wb = Workbook()
    _division_sheet(wb, joint, data)
    _grade_sheet(wb, joint, data)
    _subjects_list_sheet(wb, joint, data)
    _subject_sheets(wb, joint, data)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
