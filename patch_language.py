#!/usr/bin/env python3
"""Patch curriculum/views.py to add language toggle support."""
import re

with open('curriculum/views.py', 'r') as f:
    content = f.read()

# --- REPLACEMENT 1: lesson plan language detection ---
old_lp_lang_block = """        # ── Determine language for lesson plan (based on school level) ──
        _lp_tlm = get_tlm_teacher(request)
        _lp_school_level = _lp_tlm.school.level if _lp_tlm and _lp_tlm.school else ''
        _lp_subject_lower = subject.lower()
        _lp_school_level_lower = (_lp_school_level or '').lower()
        if 'primary' in _lp_school_level_lower:
            if _lp_subject_lower in ('english', 'english language'):
                lp_language_instruction = "LANGUAGE: Write ALL content in ENGLISH because this is an English subject for Primary school."
            else:
                lp_language_instruction = "LANGUAGE: Write ALL lesson content in KISWAHILI (Swahili). Only the headings/section titles can stay in English. ALL descriptions, activities, explanations, and assessment criteria MUST be in Swahili language. This is a Primary school subject."
        elif 'secondary' in _lp_school_level_lower or 'ordinary' in _lp_school_level_lower or 'advanced' in _lp_school_level_lower:
            if _lp_subject_lower in ('kiswahili', 'swahili'):
                lp_language_instruction = "LANGUAGE: Write ALL content in KISWAHILI (Swahili) because this is a Kiswahili subject for Secondary school."
            else:
                lp_language_instruction = "LANGUAGE: Write ALL content in ENGLISH. This is a Secondary school subject taught in English."
        else:
            lp_language_instruction = ""

        prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN"""

new_lp_lang_block = """        # ── Language: manual selection (english/kiswahili) or auto-detect ──
        _lp_tlm = get_tlm_teacher(request)
        _lp_school_level = _lp_tlm.school.level if _lp_tlm and _lp_tlm.school else ''
        _lp_language = data.get('language', getattr(_lp_tlm, 'preferred_language', 'auto') if _lp_tlm else 'auto')
        lp_language_instruction = _get_lp_language_instruction(_lp_language, subject, _lp_school_level)

        prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN"""

assert old_lp_lang_block in content, "ERROR: Lesson plan language block not found!"
content = content.replace(old_lp_lang_block, new_lp_lang_block, 1)

# --- REPLACEMENT 2: ajax_generate_all_lessons - add language to data extraction ---
old_all_lessons_data = """        teacher_name = data.get('teacher_name', '')
        school_name = data.get('school_name', '')

        # Get all topics for this subject from syllabus"""

new_all_lessons_data = """        teacher_name = data.get('teacher_name', '')
        school_name = data.get('school_name', '')
        language = data.get('language', getattr(teacher, 'preferred_language', 'auto'))

        # Get all topics for this subject from syllabus"""

assert old_all_lessons_data in content, "ERROR: ajax_generate_all_lessons data block not found!"
content = content.replace(old_all_lessons_data, new_all_lessons_data, 1)

# --- REPLACEMENT 3: ajax_generate_all_lessons - add language to prompt ---
old_all_lessons_prompt = """                prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN for a Tanzanian {education_level} classroom.

============================================
PRIME MINISTER'S OFFICE
REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT
TEACHER'S LESSON PLAN
============================================

School: {school_name or '[School Name]'}
Teacher's Name: {teacher_name}
Subject: {subject_name}
Form/Class: {full_class}
Date: {datetime.now().strftime(\"%d/%m/%Y\")}

Main Topic: {topic.name}
Sub-topic: {subtopic_name or 'N/A'}"""

new_all_lessons_prompt = """                _lp_school_level = school_obj.level if school_obj else ''
                _lp_lang_instruction = _get_lp_language_instruction(language, subject_name, _lp_school_level)

                prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN for a Tanzanian {education_level} classroom.

============================================
PRIME MINISTER'S OFFICE
REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT
TEACHER'S LESSON PLAN
============================================

School: {school_name or '[School Name]'}
Teacher's Name: {teacher_name}
Subject: {subject_name}
Form/Class: {full_class}
Date: {datetime.now().strftime(\"%d/%m/%Y\")}

Main Topic: {topic.name}
Sub-topic: {subtopic_name or 'N/A'}"""

if old_all_lessons_prompt in content:
    content = content.replace(old_all_lessons_prompt, new_all_lessons_prompt, 1)
else:
    print("WARNING: ajax_generate_all_lessons prompt block not found (1st variant)")
    # Try alternative
    alt_old = """                prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN for a Tanzanian {education_level} classroom.

============================================
PRIME MINISTER'S OFFICE"""
    alt_new = """                _lp_school_level = school_obj.level if school_obj else ''
                _lp_lang_instruction = _get_lp_language_instruction(language, subject_name, _lp_school_level)

                prompt = f\"\"\"Generate a TEACHER'S LESSON PLAN for a Tanzanian {education_level} classroom.

============================================
PRIME MINISTER'S OFFICE"""
    if alt_old in content:
        content = content.replace(alt_old, alt_new, 1)
        print("Applied alt replacement for all_lessons prompt")
    else:
        print("WARNING: All lessons prompt not found!")

# Now add language instruction to the all_lessons prompt after School/Teacher/Subject block
# Look for "Competence: Numbered format" and add language before it
old_all_lessons_after_school = """\nMain Competence: Numbered format from Tanzanian syllabus"""
new_all_lessons_after_school = f"""\n{{_lp_lang_instruction}}\n\nMain Competence: Numbered format from Tanzanian syllabus"""

# Actually, let's find where to insert the language instruction in the prompt
# Search for "Duration: {duration} minutes" in the all_lessons prompt area
old_all_lessons_duration = """\nDuration: {duration} minutes

Content MUST relate"""
new_all_lessons_duration = """\nDuration: {duration} minutes
{_lp_lang_instruction}

Content MUST relate"""

if old_all_lessons_duration in content:
    content = content.replace(old_all_lessons_duration, new_all_lessons_duration, 1)
    print("Applied duration block replacement for all_lessons")
else:
    print("WARNING: Duration block not found in all_lessons!")

# --- REPLACEMENT 4: ajax_generate_one_lesson - add language ---
old_one_lesson_data = """        teacher_name = data.get('teacher_name', '')
        school_name = data.get('school_name', '')
        topic_name = data.get('topic', '').strip()"""

new_one_lesson_data = """        teacher_name = data.get('teacher_name', '')
        school_name = data.get('school_name', '')
        language = data.get('language', getattr(teacher, 'preferred_language', 'auto'))
        topic_name = data.get('topic', '').strip()"""

assert old_one_lesson_data in content, "ERROR: ajax_generate_one_lesson data block not found!"
content = content.replace(old_one_lesson_data, new_one_lesson_data, 1)

# --- REPLACEMENT 5: ajax_generate_one_lesson - add language to prompt ---
old_one_lesson_school = """        # Handle missing school
        school_obj = teacher.school
        if not school_obj and school_name:
            school_obj = School.objects.filter(name__iexact=school_name).first()
        if not school_obj:
            return JsonResponse({'success': False, 'error': 'Shule yako haijapatikana kwenye mfumo. Sasisha wasifu wako.'}, status=400)

        # Get subject object
        subj_obj = Subject.objects.filter(id=subject_id).first() or Subject.objects.filter(name__iexact=subject_name).first()
        if not subj_obj:
            return JsonResponse({'success': False, 'error': f'Somo \"{subject_name}\" halipatikani'}, status=404)

        # Build prompt"""

new_one_lesson_school = """        # Handle missing school
        school_obj = teacher.school
        if not school_obj and school_name:
            school_obj = School.objects.filter(name__iexact=school_name).first()
        if not school_obj:
            return JsonResponse({'success': False, 'error': 'Shule yako haijapatikana kwenye mfumo. Sasisha wasifu wako.'}, status=400)

        # Get subject object
        subj_obj = Subject.objects.filter(id=subject_id).first() or Subject.objects.filter(name__iexact=subject_name).first()
        if not subj_obj:
            return JsonResponse({'success': False, 'error': f'Somo \"{subject_name}\" halipatikani'}, status=404)

        _lp_school_level = school_obj.level if school_obj else ''
        _lp_lang_instruction = _get_lp_language_instruction(language, subject_name, _lp_school_level)

        # Build prompt"""

assert old_one_lesson_school in content, "ERROR: ajax_generate_one_lesson school block not found!"
content = content.replace(old_one_lesson_school, new_one_lesson_school, 1)

# --- REPLACEMENT 6: ajax_generate_one_lesson - add language instruction to prompt ---
# Find "Duration: {duration} minutes" in one_lesson prompt
old_one_lesson_duration = """Term: {term}, Year: {year}
Duration: {duration} minutes

Content MUST relate"""
new_one_lesson_duration = """Term: {term}, Year: {year}
Duration: {duration} minutes
{_lp_lang_instruction}

Content MUST relate"""

if old_one_lesson_duration in content:
    content = content.replace(old_one_lesson_duration, new_one_lesson_duration, 1)
    print("Applied one_lesson duration replacement")
else:
    print("WARNING: one_lesson duration block not found!")

# --- REPLACEMENT 7: ajax_update_teacher_profile - save preferred_language ---
old_update_profile = """        # ── Handle theme ──
        theme = data.get('theme', '').strip()
        if theme and teacher.theme != theme:
            teacher.theme = theme
            changed = True

        if changed:
            teacher.save(update_fields=['class_name', 'stream', 'subject', 'total_boys', 'total_girls', 'theme'])"""

new_update_profile = """        # ── Handle theme ──
        theme = data.get('theme', '').strip()
        if theme and teacher.theme != theme:
            teacher.theme = theme
            changed = True

        # ── Handle preferred_language ──
        preferred_language = data.get('preferred_language', '').strip()
        if preferred_language and teacher.preferred_language != preferred_language:
            teacher.preferred_language = preferred_language
            changed = True

        if changed:
            teacher.save(update_fields=['class_name', 'stream', 'subject', 'total_boys', 'total_girls', 'theme', 'preferred_language'])"""

assert old_update_profile in content, "ERROR: ajax_update_teacher_profile block not found!"
content = content.replace(old_update_profile, new_update_profile, 1)

# Write the updated content
with open('curriculum/views.py', 'w') as f:
    f.write(content)

print("✅ All replacements applied successfully!")
