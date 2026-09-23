"""Maelekezo ya mfumo — "mfumo unaojielezea wenyewe".

Chanzo KIMOJA cha maelezo ya kila ukurasa na kila kitendo cha app ya
results, kikiwa kimefungwa kwa jina la URL (url_name):

  - Kisanduku cha "ℹ️ Ukurasa huu" juu ya kila ukurasa (base.html) kinasoma
    entry ya ukurasa uliopo: ni wa nini + hatua za kufuata.
  - Kila kiungo/kitufe kinachoelekea URL iliyo hapa kinapata maelezo
    yenyewe ("➜ Inakupeleka: …" / "⚡ Kitendo: …") — hakuna haja ya kuandika
    tooltip kwenye kila template. Kitufe chenye data-help="…" chake
    mwenyewe kinashinda maelezo haya.

kind: 'page'   → ukurasa unaofunguka (kiungo kinakupeleka huko)
      'action' → kitendo (fomu/POST) — kinabadilisha kitu kisha kinarudi
      'file'   → kinapakua / kufungua faili (PDF, Excel)

Ongeza ukurasa mpya? Ongeza entry hapa kwa jina lake la URL — basi.
"""
import json
import re

from django.urls import URLPattern, URLResolver, get_resolver


def _h(kind, sw_title, sw_what, en_title, en_what, sw_steps=(), en_steps=()):
    return {
        'kind': kind,
        'sw': {'title': sw_title, 'what': sw_what, 'steps': list(sw_steps)},
        'en': {'title': en_title, 'what': en_what, 'steps': list(en_steps)},
    }


PAGE_HELP = {
    # ── Kuingia / kujiunga ─────────────────────────────────────────────
    'results_login': _h(
        'page', 'Ingia', 'Ingia kwenye mfumo kwa barua pepe na nenosiri ulilopewa na Mtaaluma wa shule.',
        'Login', 'Sign in with the email and password your school Academic gave you.'),
    'results_logout': _h(
        'action', 'Toka', 'Unatoka kwenye mfumo. Utahitaji kuingia tena kuendelea.',
        'Logout', 'Signs you out. You will need to log in again.'),
    'register_school_start': _h(
        'page', 'Jiunge na Mfumo', 'Sajili shule yako: chagua mkoa, wilaya na shule, kisha weka taarifa za Mtaaluma.',
        'Join the System', 'Register your school: pick region, district and school, then the Academic\'s details.',
        ['Chagua mkoa na wilaya', 'Tafuta shule yako', 'Jaza taarifa za Mtaaluma na uthibitishe'],
        ['Pick region and district', 'Find your school', 'Fill in the Academic\'s details and confirm']),
    'register_school_confirm': _h(
        'page', 'Thibitisha Usajili', 'Kagua taarifa za shule kabla ya kukamilisha usajili.',
        'Confirm Registration', 'Review the school details before finishing registration.'),

    # ── Nyumbani / dashibodi ──────────────────────────────────────────
    'home': _h(
        'page', 'Mitihani (Nyumbani)', 'Orodha ya mitihani yote ya shule. Bonyeza mtihani kuona masomo yake, alama na matokeo.',
        'Exams (Home)', 'Every exam of the school. Open an exam to see its subjects, marks and results.',
        ['Tafuta mtihani kwa aina / darasa', 'Bonyeza jina la mtihani kufungua muhtasari wake'],
        ['Filter by type / class', 'Click an exam name to open its overview']),
    'academic_dashboard': _h(
        'page', 'Dashibodi ya Academic', 'Kituo kikuu cha Mtaaluma: hali ya mitihani, masomo yaliyowasilishwa, na njia za mkato za kazi zote.',
        'Academic Dashboard', 'The Academic\'s hub: exam status, submitted subjects and shortcuts to every task.',
        ['Angalia masomo yaliyowasilishwa na walimu', 'Idhinisha au rudisha masomo', 'Tengeneza PDF za matokeo darasa likikamilika'],
        ['Check the subjects teachers submitted', 'Approve or return subjects', 'Generate results PDFs once a class is complete']),
    'teacher_dashboard': _h(
        'page', 'Dashibodi ya Mwalimu', 'Masomo na madarasa yako, mitihani inayosubiri alama zako, na hali ya ulichowasilisha.',
        'Teacher Dashboard', 'Your subjects and classes, exams waiting for your marks, and the status of what you submitted.',
        ['Chagua mtihani unaosubiri alama', 'Jaza alama (Jaza Alama)', 'Wasilisha kwa Academic'],
        ['Pick an exam waiting for marks', 'Enter marks (Marks Entry)', 'Submit to the Academic']),
    'printing_secretary_dashboard': _h(
        'page', 'Uchapishaji (PS)', 'Kazi zilizotumwa kuchapishwa na Academic. Fungua PDF, chapisha, kisha weka alama "imechapishwa".',
        'Printing (PS)', 'Jobs the Academic sent for printing. Open the PDF, print it, then mark it printed.'),
    'user_guide': _h(
        'page', 'Mwongozo', 'Mwongozo kamili wa kutumia mfumo, hatua kwa hatua, kwa kila aina ya mtumiaji.',
        'User Guide', 'The full step-by-step guide for every kind of user.'),

    # ── Shule ─────────────────────────────────────────────────────────
    'school_setup': _h(
        'page', 'Shule Yangu', 'Taarifa za shule, nembo, masomo na mipangilio ya mwaka wa masomo.',
        'My School', 'School details, logos, subjects and academic-year settings.'),
    'school_subjects': _h(
        'page', 'Masomo ya Shule', 'Chagua masomo yanayofundishwa shuleni na madarasa yake. Mtihani mpya unachukua masomo haya.',
        'School Subjects', 'Pick the subjects taught at the school and their classes. New exams use this list.'),
    'upload_logos': _h(
        'page', 'Nembo', 'Pakia nembo ya shule na ya halmashauri — zinaonekana juu ya kila PDF ya matokeo.',
        'Logos', 'Upload the school and council logos shown at the top of every results PDF.'),
    'manage_teachers': _h(
        'page', 'Simamia Walimu', 'Ongeza walimu, wape masomo na madarasa, badilisha au futa akaunti zao.',
        'Manage Teachers', 'Add teachers, assign their subjects and classes, edit or remove accounts.'),
    'assign_teacher_form': _h(
        'page', 'Mpe Mwalimu Darasa', 'Mpe mwalimu somo na darasa atakalojaza alama zake.',
        'Assign Teacher', 'Give a teacher the subject and class they enter marks for.'),
    'select_my_subjects': _h(
        'page', 'Masomo Yangu', 'Chagua masomo na madarasa unayofundisha — ndiyo yatakayoonekana kwenye Jaza Alama.',
        'My Subjects', 'Pick the subjects and classes you teach — they are what Marks Entry shows you.'),
    'year_rollover': _h(
        'page', 'Anza Mwaka Mpya', 'Pandisha wanafunzi darasa moja juu na anza mwaka mpya wa masomo. Wa mwisho (Form 4/6) wanahifadhiwa.',
        'Start New Year', 'Promote every student one class up and start the new academic year. Leavers are archived.'),
    'school_storage': _h(
        'page', 'Hifadhi ya Shule', 'Wanafunzi waliohifadhiwa (waliomaliza/walioondolewa). Unaweza kumrudisha mmoja kwenye orodha.',
        'School Storage', 'Archived students (graduated/removed). You can restore one to the roster.'),
    'restore_storage_student': _h(
        'action', 'Rudisha Mwanafunzi', 'Anarudishwa kwenye orodha ya darasa lake.',
        'Restore Student', 'Puts the student back on their class roster.'),

    # ── Wanafunzi (roster) ─────────────────────────────────────────────
    'upload_form_students': _h(
        'page', 'Orodha ya Wanafunzi', 'Orodha rasmi ya wanafunzi wa kila darasa. Kila sehemu ya mfumo (alama, scoresheet, PDF) inaitumia.',
        'Student Roster', 'The official student list of each class. Marks, scoresheets and PDFs all use it.',
        ['Chagua darasa', 'Pakia faili (Excel/PDF), scan karatasi au ongeza mmoja mmoja', 'Rekebisha jinsia na masomo ya kila mwanafunzi'],
        ['Choose a class', 'Upload a file (Excel/PDF), scan a sheet or add one by one', 'Fix each student\'s gender and subjects']),
    'upload_roster': _h(
        'action', 'Pakia Orodha', 'Pakia faili la orodha ya wanafunzi (Excel/PDF/Word) kwa darasa ulilochagua.',
        'Upload Roster', 'Upload a student list file (Excel/PDF/Word) for the chosen class.'),
    'download_roster_template': _h(
        'file', 'Pakua Kiolezo', 'Pakua faili la Excel la mfano — jaza majina humo kisha lipakie.',
        'Download Template', 'Download a sample Excel file — fill in the names and upload it.'),
    'scan_roster': _h(
        'page', 'Scan Orodha', 'Piga picha ya orodha ya wanafunzi iliyoandikwa — mfumo unasoma majina yenyewe.',
        'Scan Roster', 'Photograph a written student list — the system reads the names for you.'),
    'save_scanned_roster': _h(
        'action', 'Hifadhi Orodha Iliyoscaniwa', 'Majina uliyoyakagua yanaingizwa kwenye orodha ya darasa.',
        'Save Scanned Roster', 'The names you checked are added to the class roster.'),
    'delete_form_student': _h(
        'action', 'Futa Mwanafunzi', 'Unaulizwa kwanza. Unaweza pia kumwondoa kwenye matokeo ya mitihani ya darasa lake.',
        'Delete Student', 'You are asked first. You can also remove them from that class\'s exam results.'),
    'delete_all_form_students': _h(
        'action', 'Futa Wote wa Darasa', 'Inafuta orodha YOTE ya darasa hili. Tumia kwa uangalifu mkubwa.',
        'Delete Whole Class', 'Deletes the WHOLE roster of this class. Use with great care.'),
    'edit_form_student': _h(
        'action', 'Hariri Mwanafunzi', 'Badilisha jina, jinsia au namba ya mwanafunzi.',
        'Edit Student', 'Change the student\'s name, gender or number.'),
    'assign_form_student_subjects': _h(
        'action', 'Masomo ya Mwanafunzi', 'Chagua masomo ya hiari anayosoma mwanafunzi huyu.',
        'Student Subjects', 'Pick the optional subjects this student takes.'),
    'bulk_edit_form_student_gender': _h(
        'action', 'Badilisha Jinsia (Wengi)', 'Weka jinsia ya wanafunzi wengi uliowachagua kwa pamoja.',
        'Bulk Edit Gender', 'Set the gender of all selected students at once.'),
    'bulk_assign_form_student_subjects': _h(
        'action', 'Masomo kwa Wengi', 'Wape wanafunzi wote uliowachagua masomo yaleyale kwa pamoja.',
        'Bulk Assign Subjects', 'Give every selected student the same subjects at once.'),

    # ── Mitihani ──────────────────────────────────────────────────────
    'upload_results': _h(
        'page', 'Unda Mtihani Mpya', 'Tengeneza mtihani mpya: jina, darasa, aina na masomo yake. Walimu wataona mtihani huu kujaza alama.',
        'Create New Exam', 'Create a new exam: name, class, type and subjects. Teachers then see it to enter marks.',
        ['Weka jina, mwaka na darasa', 'Chagua aina ya mtihani', 'Chagua masomo kisha Unda'],
        ['Enter name, year and class', 'Choose the exam type', 'Pick the subjects and Create']),
    'create_exam_for_school': _h(
        'page', 'Unda Mtihani', 'Tengeneza mtihani mpya kwa darasa — masomo ya shule yanaongezwa yenyewe.',
        'Create Exam', 'Create a new exam for a class — the school\'s subjects are added automatically.'),
    'exam_overview': _h(
        'page', 'Muhtasari wa Mtihani', 'Kila somo la mtihani huu na hali yake (linasubiri / limewasilishwa / limeidhinishwa), pamoja na vitendo vyote vya mtihani.',
        'Exam Overview', 'Every subject of this exam with its status (pending / submitted / approved) and every exam action.',
        ['Angalia masomo yaliyobaki', 'Idhinisha masomo yaliyowasilishwa', 'Tengeneza PDF ya matokeo'],
        ['See which subjects are still pending', 'Approve submitted subjects', 'Generate the results PDF']),
    'delete_exam': _h(
        'action', 'Futa Mtihani', 'Inafuta mtihani huu pamoja na alama zake zote. Haiwezi kurudishwa.',
        'Delete Exam', 'Deletes this exam with all its marks. Cannot be undone.'),
    'finalize_exam': _h(
        'action', 'Kamilisha Mtihani', 'Mtihani unafungwa — alama hazibadilishwi tena.',
        'Finalize Exam', 'Locks the exam — marks can no longer change.'),
    'approve_exam_submissions': _h(
        'action', 'Idhinisha Masomo Yote', 'Inaidhinisha kila somo lililowasilishwa kwenye mtihani huu kwa pamoja.',
        'Approve All', 'Approves every submitted subject of this exam at once.'),
    'approve_subject': _h(
        'action', 'Idhinisha Somo', 'Alama za somo hili zinakubaliwa na kuingia kwenye matokeo.',
        'Approve Subject', 'Accepts this subject\'s marks into the results.'),
    'return_submission': _h(
        'action', 'Rudisha kwa Mwalimu', 'Somo linarudishwa kwa mwalimu ili arekebishe alama.',
        'Return to Teacher', 'Sends the subject back to the teacher to fix the marks.'),
    'recompute_exam_results': _h(
        'action', 'Hesabu Upya', 'Inahesabu upya jumla, wastani, daraja na nafasi za wanafunzi wote.',
        'Recompute', 'Recalculates every student\'s total, average, division and position.'),
    'academic_add_student_marks': _h(
        'page', 'Ongeza Mwanafunzi & Alama', 'Chagua mtihani na mwanafunzi, jaza au rekebisha alama za masomo yote, ongeza somo, au mwondoe mwanafunzi kwenye matokeo.',
        'Add Student & Marks', 'Pick an exam and a student, enter or fix marks for every subject, add a subject, or remove a student from the results.',
        ['Chagua mtihani', 'Chagua mwanafunzi (au ongeza mpya)', 'Jaza alama kisha Hifadhi'],
        ['Choose the exam', 'Choose the student (or add a new one)', 'Enter the marks and Save']),
    'set_class_teacher': _h(
        'page', 'Mwalimu wa Darasa', 'Chagua mwalimu wa darasa kwa mtihani huu — ndiye anayejaza tabia na maoni.',
        'Class Teacher', 'Choose this exam\'s class teacher — they fill in conduct and comments.'),
    'set_conduct_and_comments': _h(
        'page', 'Tabia na Maoni', 'Jaza tabia (A–F) na maoni ya mwalimu kwa kila mwanafunzi — yanaonekana kwenye ripoti yake.',
        'Conduct & Comments', 'Enter conduct grades (A–F) and teacher comments for each student — shown on their report.'),
    'submit_exam_to_ps': _h(
        'action', 'Tuma kwa PS', 'PDF ya matokeo inatumwa kwa Katibu Muhtasi (PS) kuchapishwa.',
        'Send to PS', 'Sends the results PDF to the Printing Secretary to print.'),
    'exam_share_links': _h(
        'page', 'Viungo vya Wazazi', 'Viungo/QR vya kila mwanafunzi — mzazi anaona matokeo ya mtoto wake tu.',
        'Parent Links', 'Per-student links/QR codes — a parent sees only their own child\'s result.'),

    # ── Masomo ya mtihani ─────────────────────────────────────────────
    'subject_upload': _h(
        'page', 'Pakia Alama za Somo', 'Pakia faili la alama za somo hili (Excel/PDF/picha).',
        'Upload Subject Marks', 'Upload this subject\'s marks file (Excel/PDF/photo).'),
    'subject_pdf': _h(
        'file', 'PDF ya Somo', 'Fungua PDF ya alama za somo hili kwa wanafunzi wote.',
        'Subject PDF', 'Opens the PDF of this subject\'s marks for every student.'),
    'subject_summary': _h(
        'page', 'Muhtasari wa Somo', 'Takwimu za somo: wastani, alama za juu/chini, madaraja na walioshindwa.',
        'Subject Summary', 'Subject statistics: average, highest/lowest, grades and failures.'),
    'bulk_scoresheet_upload': _h(
        'page', 'Scan Scoresheet (Academic)', 'Pakia picha/PDF ya scoresheet ya somo — mfumo unasoma alama na kumpangia kila mwanafunzi kwa jina lake. Kagua kisha hifadhi.',
        'Scan Scoresheets (Academic)', 'Upload a subject scoresheet photo/PDF — marks are read and matched to each student by name. Review, then save.',
        ['Chagua somo', 'Pakia picha au PDF', 'Kagua jedwali kisha Hifadhi'],
        ['Choose the subject', 'Upload the photo or PDF', 'Review the table and Save']),
    'save_confirmed_scores': _h(
        'action', 'Hifadhi Alama', 'Alama ulizokagua zinahifadhiwa na somo linaidhinishwa.',
        'Save Marks', 'Saves the reviewed marks and approves the subject.'),
    'bulk_scoresheet_preview_pdf': _h(
        'file', 'Hakiki PDF', 'Angalia PDF ya alama zilizosomwa kabla ya kuhifadhi.',
        'Preview PDF', 'See a PDF of the read marks before saving.'),

    # ── Matokeo / PDF ─────────────────────────────────────────────────
    'generate_results_pdf': _h(
        'file', 'PDF ya Matokeo ya Darasa', 'Ripoti ya matokeo ya darasa zima: muhtasari wa madaraja, takwimu za masomo, na orodha ya wanafunzi wote.',
        'Class Results PDF', 'The whole-class results report: division summary, subject stats and every student.'),
    'generate_bulk_student_results_pdf': _h(
        'file', 'Ripoti za Wanafunzi Wote', 'PDF moja yenye ripoti (result slip) ya kila mwanafunzi, ukurasa wake.',
        'All Student Reports', 'One PDF with every student\'s result slip, each on its own page.'),
    'export_results_excel': _h(
        'file', 'Excel ya Matokeo', 'Pakua matokeo ya mtihani huu kama Excel.',
        'Results Excel', 'Download this exam\'s results as Excel.'),
    'form_results': _h(
        'page', 'Matokeo ya Darasa', 'Mitihani yote ya darasa hili na hali yake — fungua PDF, Excel au ripoti za wanafunzi.',
        'Class Results', 'Every exam of this class and its status — open PDFs, Excel or student reports.'),
    'form_results_excel': _h(
        'file', 'Excel ya Darasa', 'Pakua matokeo ya mitihani yote ya darasa hili kama Excel.',
        'Class Excel', 'Download every exam result of this class as Excel.'),
    'teacher_performance_report': _h(
        'file', 'Ripoti ya Walimu', 'Ufaulu wa kila somo kwa mwalimu wake, kwa darasa hili.',
        'Teacher Report', 'Pass rates of each subject by its teacher, for this class.'),
    'student_results_search': _h(
        'page', 'Tafuta Matokeo', 'Tafuta matokeo ya mwanafunzi kwa jina lake.',
        'Search Results', 'Look up a student\'s results by name.'),
    'student_result_public': _h(
        'page', 'Matokeo ya Mwanafunzi', 'Ripoti ya mwanafunzi mmoja — masomo, alama, daraja na nafasi.',
        'Student Result', 'One student\'s report — subjects, marks, division and position.'),
    'student_result_pdf': _h(
        'file', 'PDF ya Mwanafunzi', 'Pakua ripoti ya mwanafunzi huyu kama PDF.',
        'Student PDF', 'Download this student\'s report as a PDF.'),
    'edit_processed_result': _h(
        'page', 'Hariri Matokeo', 'Rekebisha matokeo ya mwanafunzi mmoja (mf. tabia au maoni).',
        'Edit Result', 'Fix one student\'s result (e.g. conduct or comments).'),
    'result_verify': _h(
        'page', 'Thibitisha Matokeo', 'Thibitisha kuwa ripoti hii ni halali na imetoka kwenye mfumo.',
        'Verify Result', 'Confirms this report is genuine and came from the system.'),
    'result_verify_regenerate': _h(
        'action', 'QR Mpya', 'Inatengeneza QR mpya ya uthibitisho — ile ya zamani haitafanya kazi tena.',
        'New QR', 'Creates a new verification QR — the old one stops working.'),
    'ps_pdf_inline': _h(
        'file', 'Fungua PDF', 'Fungua PDF iliyotumwa kuchapishwa.',
        'Open PDF', 'Opens the PDF sent for printing.'),
    'ps_print_view': _h(
        'page', 'Chapisha', 'Ukurasa wa kuchapisha kazi hii.',
        'Print', 'The print view of this job.'),

    # ── Jaza alama (mwalimu) ─────────────────────────────────────────
    'marks_entry': _h(
        'page', 'Jaza Alama', 'Chagua mtihani, somo na darasa — kisha andika alama, scan scoresheet, au tumia sauti. Ukimaliza, wasilisha kwa Academic.',
        'Marks Entry', 'Pick exam, subject and class — then type marks, scan a scoresheet or use voice. When done, submit to the Academic.',
        ['Chagua mtihani, somo na darasa, bonyeza Continue', 'Jaza alama (0–100, au X kwa asiyefanya)', 'Hifadhi, kisha Wasilisha'],
        ['Choose exam, subject and class, press Continue', 'Enter marks (0–100, or X if absent)', 'Save, then Submit']),
    'marks_entry_save': _h(
        'action', 'Hifadhi Alama', 'Alama zinahifadhiwa — bado unaweza kuzibadilisha kabla ya kuwasilisha.',
        'Save Marks', 'Saves the marks — you can still change them before submitting.'),
    'marks_entry_submit': _h(
        'action', 'Wasilisha kwa Academic', 'Somo linatumwa kwa Academic kuidhinishwa. Hutaweza kubadilisha mpaka akurudishie.',
        'Submit to Academic', 'Sends the subject to the Academic for approval. You can\'t edit until it is returned.'),
    'marks_entry_add_student': _h(
        'action', 'Ongeza Mwanafunzi', 'Ongeza mwanafunzi aliyesahaulika kwenye orodha ya darasa hili.',
        'Add Student', 'Add a missing student to this class list.'),
    'scoresheet_photo_extract': _h(
        'action', 'Scan Scoresheet', 'Piga picha ya scoresheet — alama zinasomwa na kumpangia kila mwanafunzi kwa jina lake. Kagua kabla ya kuhifadhi.',
        'Scan Scoresheet', 'Photograph the scoresheet — marks are read and matched to each student by name. Check before saving.'),
    'marks_entry_preview_pdf': _h(
        'file', 'Hakiki PDF', 'Angalia PDF ya alama ulizojaza kabla ya kuwasilisha.',
        'Preview PDF', 'See a PDF of the marks you entered before submitting.'),
    'download_scoresheet_names_pdf': _h(
        'file', 'Pakua Scoresheet', 'PDF ya majina ya wanafunzi yenye nafasi ya kuandika alama — chapisha, jaza kwa mkono, kisha scan.',
        'Download Scoresheet', 'A PDF of student names with space for marks — print, fill by hand, then scan.'),
    'speech_entry_page': _h(
        'page', 'Jaza kwa Sauti', 'Soma jina na alama kwa sauti — mfumo unaandika wenyewe.',
        'Voice Entry', 'Read out name and mark — the system types them in.'),
    'guided_voice_entry': _h(
        'page', 'Sauti (Hatua kwa Hatua)', 'Mfumo unakutajia mwanafunzi mmoja mmoja, unasema alama yake.',
        'Guided Voice Entry', 'The system reads each student in turn and you say their mark.'),
    'personal_upload': _h(
        'page', 'Binafsi', 'Pakia alama zako binafsi (nje ya mitihani ya shule) upate PDF na muhtasari.',
        'Personal', 'Upload your own marks (outside school exams) to get a PDF and summary.'),
    'necta_ca_form': _h(
        'page', 'NECTA CA', 'Tengeneza fomu ya alama za CA (Continuous Assessment) ya NECTA.',
        'NECTA CA', 'Generate the NECTA Continuous Assessment marks form.'),

    # ── Ratiba ────────────────────────────────────────────────────────
    'class_timetable_view': _h(
        'page', 'Ratiba ya Darasa', 'Angalia ratiba ya vipindi vya kila darasa. Academic anaweza kuihariri, kuipakua au kuituma kwa PS.',
        'Class Timetable', 'View each class\'s lesson timetable. The Academic can edit, download or send it to PS.'),
    'time_slot_setup': _h(
        'page', 'Vipindi vya Siku', 'Weka muda wa kila kipindi na mapumziko.',
        'Time Slots', 'Set the time of each period and break.'),
    'teaching_assignment_manage': _h(
        'page', 'Mgawanyo wa Vipindi', 'Nani anafundisha nini, darasa gani, vipindi vingapi kwa wiki.',
        'Teaching Assignments', 'Who teaches what, in which class, how many periods a week.'),
    'generate_class_timetable': _h(
        'page', 'Tengeneza Ratiba', 'Mfumo unapanga ratiba yenyewe kutoka kwenye mgawanyo wa vipindi.',
        'Generate Timetable', 'The system builds the timetable from the teaching assignments.'),
    'timetable_download_pdf': _h(
        'file', 'PDF ya Ratiba', 'Pakua ratiba kama PDF.',
        'Timetable PDF', 'Download the timetable as a PDF.'),
    'timetable_send_to_ps': _h(
        'action', 'Tuma Ratiba kwa PS', 'Ratiba inatumwa kwa Katibu Muhtasi kuchapishwa.',
        'Send Timetable to PS', 'Sends the timetable to the Printing Secretary.'),
    'delete_class_timetable': _h(
        'action', 'Futa Ratiba', 'Inafuta ratiba iliyopo.',
        'Delete Timetable', 'Deletes the current timetable.'),

    # ── Malipo ────────────────────────────────────────────────────────
    'choose_plan': _h(
        'page', 'Malipo', 'Chagua kifurushi cha kulipia matumizi ya mfumo.',
        'Billing', 'Choose a plan to pay for the system.'),

    # ── Sahishi (scan & sahihisha) ───────────────────────────────────
    'scan_answer_key': _h(
        'page', 'Sahishi: Majibu Sahihi', 'Weka majibu sahihi ya mtihani wa kuchagua (multiple choice).',
        'Sahishi: Answer Key', 'Enter the correct answers of the multiple-choice test.'),
    'scan_print': _h(
        'page', 'Sahishi: Chapisha Karatasi', 'Chapisha karatasi za majibu za wanafunzi.',
        'Sahishi: Print Sheets', 'Print the students\' answer sheets.'),
    'scan_upload': _h(
        'page', 'Sahishi: Pakia Karatasi', 'Pakia picha za karatasi zilizojazwa — zinasahihishwa zenyewe.',
        'Sahishi: Upload Sheets', 'Upload photos of the filled sheets — they are marked automatically.'),
    'scan_review': _h(
        'page', 'Sahishi: Kagua', 'Kagua karatasi zilizosahihishwa na urekebishe zenye shaka.',
        'Sahishi: Review', 'Review the marked sheets and fix doubtful ones.'),
    'scan_results': _h(
        'page', 'Sahishi: Matokeo', 'Alama za kila mwanafunzi kutoka karatasi zilizosahihishwa.',
        'Sahishi: Results', 'Each student\'s score from the marked sheets.'),
    'scan_import': _h(
        'action', 'Sahishi: Ingiza Alama', 'Alama za Sahishi zinaingizwa kwenye mtihani huu.',
        'Sahishi: Import', 'Imports the Sahishi scores into this exam.'),
    'scan_scheme_upload': _h(
        'page', 'Sahishi: Pakia Mwongozo', 'Pakia mwongozo wa kusahihisha (marking scheme) wa somo hili.',
        'Sahishi: Upload Scheme', 'Upload the marking scheme for this subject.'),
    'scan_scheme_print': _h(
        'file', 'Sahishi: Chapisha Mwongozo', 'Fungua mwongozo wa kusahihisha tayari kuchapishwa.',
        'Sahishi: Print Scheme', 'Opens the marking scheme ready to print.'),
    'scan_review_pdf': _h(
        'file', 'Sahishi: PDF ya Karatasi', 'PDF ya karatasi zote zilizosahihishwa, zikiwa na alama za vema/kosa.',
        'Sahishi: Marked PDF', 'A PDF of every marked sheet with ticks and crosses.'),
    'scan_sheet_image': _h(
        'file', 'Picha ya Karatasi', 'Fungua picha asili ya karatasi hii.',
        'Sheet Photo', 'Opens the original photo of this sheet.'),
    'scan_sheet_annotated': _h(
        'file', 'Karatasi Iliyosahihishwa', 'Fungua karatasi hii ikiwa na alama za vema/kosa.',
        'Marked Sheet', 'Opens this sheet with ticks and crosses.'),
    'scan_sheet_confirm': _h(
        'action', 'Thibitisha Karatasi', 'Unakubali alama za karatasi hii kuwa sahihi.',
        'Confirm Sheet', 'Accepts this sheet\'s score as correct.'),
    'scan_sheet_delete': _h(
        'action', 'Futa Karatasi', 'Inafuta karatasi hii iliyopakiwa (mf. picha mbaya) ili uipakie upya.',
        'Delete Sheet', 'Deletes this uploaded sheet (e.g. a bad photo) so you can upload it again.'),
    'bridge_page': _h(
        'page', 'Sahishi: Kompyuta ya Scanner', 'Tuma kazi ya kusahihisha kwa kompyuta iliyounganishwa na scanner ya shule.',
        'Sahishi: Scanner PC', 'Send a marking job to the computer connected to the school scanner.'),
    'bridge_start_job': _h(
        'action', 'Anza Kusahihisha', 'Kazi inatumwa kwa kompyuta ya scanner — subiri hali ibadilike kuwa "imekamilika".',
        'Start Marking', 'Sends the job to the scanner PC — wait for the status to turn "done".'),
    'personal_upload_pdf': _h(
        'file', 'PDF Binafsi', 'Pakua PDF ya alama ulizopakia binafsi.',
        'Personal PDF', 'Download the PDF of the marks you uploaded.'),
    'personal_upload_summary': _h(
        'page', 'Muhtasari Binafsi', 'Takwimu za alama ulizopakia binafsi: wastani, madaraja, waliofaulu.',
        'Personal Summary', 'Statistics of your uploaded marks: average, grades, passes.'),
    'pay_for_plan': _h(
        'page', 'Lipia Kifurushi', 'Weka namba ya simu ya kulipia — utapokea ujumbe wa kuthibitisha malipo kwenye simu yako.',
        'Pay for Plan', 'Enter the phone number to pay from — you will get a prompt on your phone to confirm.'),
    'payment_pending': _h(
        'page', 'Malipo Yanasubiri', 'Thibitisha malipo kwenye simu yako. Ukurasa huu unajisasisha malipo yakikamilika.',
        'Payment Pending', 'Confirm the payment on your phone. This page updates itself once it completes.'),
    'necta_ca_download': _h(
        'file', 'Pakua Fomu ya CA', 'Pakua fomu ya NECTA CA uliyoijaza.',
        'Download CA Form', 'Download the NECTA CA form you filled in.'),
    'timetable_ps_pdf_inline': _h(
        'file', 'PDF ya Ratiba', 'Fungua ratiba iliyotumwa kuchapishwa.',
        'Timetable PDF', 'Opens the timetable sent for printing.'),
    'timetable_ps_print_view': _h(
        'page', 'Chapisha Ratiba', 'Ukurasa wa kuchapisha ratiba hii.',
        'Print Timetable', 'The print view of this timetable.'),
    'filter_exams': _h(
        'page', 'Chuja Mitihani', 'Inaonyesha mitihani inayolingana na ulichochagua.',
        'Filter Exams', 'Shows the exams matching what you picked.'),
}


# ── Menyu ────────────────────────────────────────────────────────────────
# Chanzo kimoja cha menyu (kompyuta + simu). Jina na maelezo ya kila kiungo
# yanatoka PAGE_HELP hapo juu, kwa hiyo menyu inajielezea yenyewe: kila
# kiungo kinaonyesha kinakupeleka wapi. 'roles' = nani anakiona.
# (url_name, ikoni ya Font Awesome, roles)
_A, _T, _P = 'academic', 'teacher', 'ps'
NAV = [
    ('mitihani', 'fa-file-signature', 'Mitihani na Alama', 'Exams & Marks', [
        ('home', 'fa-list-check', {_A, _T}),
        ('upload_results', 'fa-plus-circle', {_A}),
        ('academic_dashboard', 'fa-chart-bar', {_A}),
        ('teacher_dashboard', 'fa-chalkboard-teacher', {_T}),
        ('marks_entry', 'fa-pen-to-square', {_A, _T}),
        ('academic_add_student_marks', 'fa-user-pen', {_A}),
        ('necta_ca_form', 'fa-file-lines', {_A, _T}),
        ('personal_upload', 'fa-file-arrow-up', {_T}),
    ]),
    ('shule', 'fa-school', 'Shule', 'School', [
        ('school_setup', 'fa-school', {_A}),
        ('upload_form_students', 'fa-user-graduate', {_A}),
        ('manage_teachers', 'fa-users', {_A}),
        ('school_subjects', 'fa-book', {_A}),
        ('select_my_subjects', 'fa-book-open-reader', {_A, _T}),
        ('class_timetable_view', 'fa-calendar-days', {_A, _T}),
    ]),
    ('ps', 'fa-print', 'Uchapishaji', 'Printing', [
        ('printing_secretary_dashboard', 'fa-print', {_P}),
    ]),
    ('msaada', 'fa-circle-question', 'Msaada', 'Help', [
        ('student_results_search', 'fa-magnifying-glass', {_A, _T, _P}),
        ('user_guide', 'fa-book-open', {_A, _T, _P}),
    ]),
]


# ── Njia ya kazi ("uko hatua gani") ─────────────────────────────────────
# Mtiririko wa kazi wa kila aina ya mtumiaji, kwa mpangilio. Unaonyeshwa juu
# ya ukurasa ukiwa kwenye hatua mojawapo au kwenye dashibodi yako.
# (url_name, jina fupi sw, jina fupi en)
WORKFLOW = {
    _A: [
        ('school_setup', 'Weka taarifa za shule', 'Set up the school'),
        ('upload_form_students', 'Pakia wanafunzi', 'Upload students'),
        ('manage_teachers', 'Ongeza walimu', 'Add teachers'),
        ('upload_results', 'Unda mtihani', 'Create an exam'),
        ('marks_entry', 'Alama zijazwe', 'Get marks entered'),
        ('academic_dashboard', 'Idhinisha & toa PDF', 'Approve & print PDFs'),
    ],
    _T: [
        ('select_my_subjects', 'Chagua masomo yako', 'Pick your subjects'),
        ('marks_entry', 'Jaza alama', 'Enter marks'),
        ('teacher_dashboard', 'Wasilisha & fuatilia', 'Submit & track'),
    ],
}
_WORKFLOW_HOME = {'home', 'academic_dashboard', 'teacher_dashboard'}


def _workflow(role, lang, current):
    from django.urls import NoReverseMatch, reverse

    steps = WORKFLOW.get(role)
    names = [s[0] for s in steps or ()]
    if not steps or (current not in names and current not in _WORKFLOW_HOME):
        return None
    out = []
    for i, (name, sw, en) in enumerate(steps, 1):
        try:
            url = reverse(name)
        except NoReverseMatch:
            continue
        out.append({'n': i, 'url': url, 'title': sw if lang == 'sw' else en,
                    'what': PAGE_HELP[name][lang]['what'], 'active': name == current})
    return {'steps': out, 'total': len(out),
            'current': next((s['n'] for s in out if s['active']), None)}


def _role(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    for attr, role in (('is_academic', _A), ('is_teacher', _T), ('is_printing_secretary', _P)):
        val = getattr(user, attr, False)
        if callable(val):
            val = val()
        if val:
            return role
    return None


def _nav(request, lang, current):
    from django.urls import NoReverseMatch, reverse

    role = _role(getattr(request, 'user', None))
    if role is None:
        return [], None
    groups, crumb = [], None
    for key, icon, sw, en, items in NAV:
        links = []
        for name, item_icon, roles in items:
            if role not in roles:
                continue
            try:
                url = reverse(name)
            except NoReverseMatch:
                continue
            h = PAGE_HELP[name][lang]
            active = name == current
            links.append({'url': url, 'icon': item_icon, 'title': h['title'],
                          'what': h['what'], 'active': active})
            if active:
                crumb = sw if lang == 'sw' else en
        if links:
            groups.append({'key': key, 'icon': icon, 'title': sw if lang == 'sw' else en,
                           'items': links, 'active': any(l['active'] for l in links)})
    return groups, crumb

# Python named groups → plain groups (JS RegExp has no (?P<name>…)).
_NAMED_GROUP = re.compile(r'\(\?P<\w+>')


def _walk(patterns, prefix=''):
    for p in patterns:
        regex = _NAMED_GROUP.sub('(', p.pattern.regex.pattern)
        regex = regex.lstrip('^').replace(r'\Z', '').rstrip('$')
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + regex)
        elif isinstance(p, URLPattern) and p.name:
            yield p.name, prefix + regex


_ROUTES = None


def _routes():
    """[(url_name, full_path_regex)] for every URL named in PAGE_HELP —
    built once from the live resolver, so a changed path in urls.py can
    never desync from the help text."""
    global _ROUTES
    if _ROUTES is None:
        # Only the results app (mounted at shule/) — other apps reuse names
        # like 'home'.
        _ROUTES = [(n, rx) for n, rx in _walk(get_resolver().url_patterns)
                   if n in PAGE_HELP and rx.startswith('shule/')]
    return _ROUTES


def page_help(request):
    """Context processor: help for the current page + the JS route map."""
    # Lugha ile ile ya field_app.context_processors.language (LANG).
    try:
        lang = 'sw' if request.session.get('ui_lang', 'en') == 'sw' else 'en'
    except Exception:
        lang = 'en'
    match = getattr(request, 'resolver_match', None)
    name = match.url_name if match else None
    entry = PAGE_HELP.get(name)
    route_map = [
        {'re': '^/' + rx + '$', 'kind': PAGE_HELP[n]['kind'],
         'title': PAGE_HELP[n][lang]['title'], 'what': PAGE_HELP[n][lang]['what']}
        for n, rx in _routes()
    ]
    nav_groups, crumb = _nav(request, lang, name)
    workflow = _workflow(_role(getattr(request, 'user', None)), lang, name)
    return {
        'WORKFLOW': workflow,
        'PAGE_HELP': entry[lang] if entry and entry['kind'] == 'page' else None,
        'PAGE_HELP_KEY': name or '',
        'NAV_GROUPS': nav_groups,
        'NAV_CRUMB': crumb,
        'PAGE_HELP_ROUTES_JSON': json.dumps(route_map).replace('<', '\\u003c'),
    }
