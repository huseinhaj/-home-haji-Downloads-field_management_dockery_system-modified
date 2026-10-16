"""Selectors za ESS (e-Utendaji) — chanzo kimoja kwa fill/approve/probe.

Zote zimethibitishwa dhidi ya DOM halisi ya ESS (Angular Material MDC).
Ikiwa portal itabadilika, haki ndipo kurekebishe — kisha endesha:

    python manage.py ess_probe --profile <id>

Zimehamishwa kutoka `essfill.py` ili zisambazwe mahali pamoja (hakuna
mabadiliko ya tabia — `essfill` bado ina `SELECTORS` kama zamani).
"""
from __future__ import annotations

# ── Login ────────────────────────────────────────────────────────────
PASSWORD_SEL = "input[formcontrolname='password'], input[name='password'], input[type='password']"

USERNAME_SELS = [
    "input[formcontrolname='username']",
    "input[formcontrolname='email']",
    "input[type='email']",
    "input[name='username']",
    "input[name='email']",
    "input[id='username']",
    "input[id='email']",
    "input.form-control:not([type='password'])",
]

# ── Sub-tasks table + menyu ya Actions ───────────────────────────────
SELECTORS = {
    'row_selector': 'table tbody tr.mat-mdc-row.mdc-data-table__row',
    'subtask_cell_selector': 'td.mat-column-subTaskDescription',
    'percentage_cell_selector': 'td.mat-column-progressPercentage',
    'percentage_value_selector': 'mat-progress-bar',
    'percentage_value_attr': 'aria-valuenow',
    'row_action_button_selector': 'td.mat-column-manage .mat-mdc-menu-trigger',
    'add_entry_labels': ['Add Sub Task Progress', 'Add Progress Details',
                         'Add Progress', 'Add Implementation'],
    'view_impl_labels': ['View Implementation', 'View Progress', 'View Impl'],
    'submit_entry_labels': ['Submit', 'SUBMIT', 'Submit Progress', 'Wasilisha',
                            'Tuma', 'Send'],
    'delete_entry_labels': ['Delete', 'Remove', 'Futa', 'Ondoa'],
    'delete_confirm_labels': ['Yes', 'YES', 'Delete', 'Confirm', 'Ok', 'OK',
                              'Continue', 'Ndiyo', 'Thibitisha', 'Futa',
                              'Proceed', 'Submit', 'SUBMIT'],
    'progress_row_selector': 'mat-dialog-container table tbody tr',
    'dialog_selector': 'mat-dialog-container',
    'subtype_select_selector': "mat-dialog-container mat-select[formcontrolname='subActivityType']",
    'description_selector': "mat-dialog-container textarea[formcontrolname='description']",
    'status_select_selector': "mat-dialog-container mat-select[formcontrolname='implementationStatus']",
    'status_option_completed': 'COMPLETED',
    'status_option_in_progress': 'IN_PROGRESS',
    'status_option_not_started': 'NOT_STARTED',
    'percentage_input_selector': "mat-dialog-container input[formcontrolname='percentageRank']",
    'save_button': "mat-dialog-container button[type='submit']",
    'paginator_next_selector': '.mat-mdc-paginator-navigation-next',
    'match_threshold': 0.9,
    # Vitufe vya kuwasilisha (ESS inahitaji Submit, si Save pekee)
    'submit_labels': ['Submit', 'SUBMIT', 'Submit Progress', 'Wasilisha', 'Tuma',
                      'Thibitisha', 'Send', 'Sumit'],
    'confirm_labels': ['Yes', 'YES', 'Ok', 'OK', 'Confirm', 'Continue',
                       'Ndiyo', 'Thibitisha', 'Submit', 'SUBMIT'],
}

# ── Hatua za `ess_probe` (smoke test) ────────────────────────────────
# `name` = kitambulisho; `step` = thamani ya `state['step']` wakati wa
# hatua hiyo (hiyo ndiyo inayoonyeshwa kama `error_step`).
PROBE_CHECKS = [
    {'name': 'open', 'step': 'open',
     'desc': 'ESS inafunguka (sessions/signin)'},
    {'name': 'login_form', 'step': 'login_form',
     'desc': 'Fomu ya login inaonekana (email/username + password)'},
    {'name': 'login', 'step': 'login',
     'desc': 'Kuingia kwa ESS kwa credential za wasifu'},
    {'name': 'session', 'step': 'session',
     'desc': 'Token ya kikao imehifadhiwa (localStorage.token)'},
    {'name': 'subtasks_table', 'step': 'subtasks_table',
     'desc': 'Jedwali la sub-tasks lina safu halisi (>0)'},
    {'name': 'row_actions', 'step': 'row_actions',
     'desc': 'Safu ya kwanza ina kitufe cha Actions (menyu)'},
    {'name': 'add_progress', 'step': 'add_progress',
     'desc': 'Menyu ya Actions ina "Add Sub Task Progress" (au jina linalolingana)'},
]
