#!/usr/bin/env python3
"""
Redesign Lesson Notes page:
1. Update the AI prompt to generate LONG, detailed notebook-style summary + Q&A
2. Completely redesign the HTML template with beautiful Generate Notes UI
"""

# =============================================================================
# PART 1: Update backend prompt in views.py
# =============================================================================
with open('curriculum/views.py', 'r') as f:
    py_content = f.read()

# ── Find and replace the prompt in ajax_generate_lesson_note_from_lp ──
old_prompt_start = '        prompt = f"""You are a Tanzanian teacher creating LESSON NOTES from a completed lesson plan.'
old_prompt_end = 'Return ONLY valid JSON. No other text."""'

# Find the exact prompt boundaries
start_idx = py_content.find(old_prompt_start)
end_idx = py_content.find(old_prompt_end, start_idx)

if start_idx != -1 and end_idx != -1:
    # Build new prompt - MUCH longer, more detailed, notebook-style
    new_prompt = '''        prompt = f"""You are an expert Tanzanian teacher writing DETAILED LESSON NOTES in NOTEBOOK format.
Your notes must be EXCEPTIONALLY THOROUGH — like a teacher's personal notebook that another teacher could use to teach the same lesson.

IMPORTANT LESSON PLAN DETAILS:
Subject: {subject_name}
Class: {lp.class_name}
Topic: {lp.topic}
Subtopic: {lp.subtopic or 'N/A'}
Date: {lp.date}
Duration: {lp.duration} minutes

Main Competence: {lp.main_competence or 'N/A'}
Specific Competence: {lp.specific_competence or 'N/A'}

{lang_instruction}

Based on the above lesson plan, create EXTREMELY DETAILED lesson notes in NOTEBOOK FORMAT.
These notes should be so complete that another teacher could pick them up and teach the lesson confidently.

Write in the following STRUCTURE - every section is required:

---

📖 [TOPIC NAME] — LESSON NOTES
═══════════════════════════════════════

1. MUHTASARI / SUMMARY (3-5 long paragraphs)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Write a VERY DETAILED summary covering:
- Ufafanuzi kamili wa dhana kuu (comprehensive definition of main concepts)
- Misingi ya kinadharia (theoretical foundations)
- Maelezo ya kina kwa kila hatua (detailed step-by-step explanations)
- Mifano halisi kutoka kwenye mada (real examples from the topic)
- Viungo na mada nyingine (connections to other topics)
- Matumizi ya kivitendo (practical applications)
- Maneno muhimu na istilahi (key vocabulary and terminology)

Each paragraph should be 5-8 SENTENCES long. Be thorough and educational.

2. NUKTA MUHIMU / KEY POINTS (at least 10 bullet points)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
List the MOST important concepts the student must remember, ordered from basic to advanced.
Each point should include a SHORT EXPLANATION, not just a heading.

3. MBINU ZA UFUNDISHAJI / TEACHING METHODS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Describe the methods that worked BEST for this topic
- Nyimbo / Songs that can help students remember
- Michezo / Games for concept reinforcement
- Maswali ya haraka / Quick oral questions to ask during class
- Kazi za vikundi / Group work ideas
- Kazi za nyumbani / Homework assignments

4. TATHMINI / ASSESSMENT (5 MAJIBU SWALI / Q&A)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate 5 CHALLENGING questions with COMPLETE answers.
Questions should test: understanding, application, analysis and evaluation (not just recall).
Each answer should be 2-4 sentences explaining the concept clearly.

Question 1: [Question]
Jibu / Answer: [Detailed answer]

Question 2: [Question]
Jibu / Answer: [Detailed answer]

Question 3: [Question]
Jibu / Answer: [Detailed answer]

Question 4: [Question]
Jibu / Answer: [Detailed answer]

Question 5: [Question]
Jibu / Answer: [Detailed answer]

5. MWONGOZO / CONCLUSION
━━━━━━━━━━━━━━━━━━━━━━━━━━
- Things that went well during the lesson
- Challenges faced
- Recommendations for next lesson

OUTPUT as JSON with this exact structure:
{{
    "title": "Topic name - Lesson Notes",
    "summary_paragraphs": ["Long paragraph 1...", "Long paragraph 2...", "Long paragraph 3...", "Long paragraph 4...", "Long paragraph 5..."],
    "key_points": ["1. Concept - Explanation", "2. Concept - Explanation", ...],
    "teaching_methods": "Detailed description of teaching methods, songs, games, activities...",
    "quiz": [
        {{"question": "Question 1?", "answer": "Detailed answer 1..."}},
        {{"question": "Question 2?", "answer": "Detailed answer 2..."}},
        {{"question": "Question 3?", "answer": "Detailed answer 3..."}},
        {{"question": "Question 4?", "answer": "Detailed answer 4..."}},
        {{"question": "Question 5?", "answer": "Detailed answer 5..."}}
    ],
    "conclusion": "What went well, challenges, recommendations..."
}}

LENGTH REQUIREMENTS:
- summary_paragraphs: 5 paragraphs, each 5-8 sentences long (VERY DETAILED)
- key_points: at least 10 items
- quiz: exactly 5 questions with detailed answers (2-4 sentences each)
- teaching_methods: at least 3-4 sentences
- conclusion: 3-5 sentences

Return ONLY valid JSON. No other text."""'''

    # Replace the prompt
    old_prompt = py_content[start_idx:end_idx + len(old_prompt_end)]
    py_content = py_content.replace(old_prompt, new_prompt, 1)
    print('✅ Backend prompt updated with LONG notebook-style format + Q&A')
else:
    print('❌ Could not find the prompt in views.py')

# ── Update the response handling to use new fields ──
old_response = '''            # Format the note content
            content_parts = []
            content_parts.append("=== LESSON NOTES ===")
            content_parts.append(note_data.get('summary', ''))
            content_parts.append("")
            content_parts.append("=== TEACHER'S REFLECTION ===")
            content_parts.append(note_data.get('reflection', ''))
            content_parts.append("")
            content_parts.append("=== QUIZ QUESTIONS ===")
            for i, q in enumerate(note_data.get('quiz', []), 1):
                content_parts.append(f"{i}. {q.get('question', '')}")
                content_parts.append(f"   Jibu: {q.get('answer', '')}")
            
            note_content = '\\n'.join(content_parts)'''

new_response = '''            # Format the note content - NOTEBOOK STYLE with proper formatting
            content_parts = []
            
            # Title
            title = note_data.get('title', f"Lesson Notes - {lp.topic}")
            content_parts.append(f"📖 {title}")
            content_parts.append("")
            
            # Summary paragraphs
            content_parts.append("=" * 60)
            content_parts.append("1. MUHTASARI / SUMMARY")
            content_parts.append("=" * 60)
            paragraphs = note_data.get('summary_paragraphs', [])
            if not paragraphs and note_data.get('summary'):
                paragraphs = [note_data['summary']]
            for para in paragraphs:
                content_parts.append(para)
                content_parts.append("")
            
            # Key points
            key_points = note_data.get('key_points', [])
            if key_points:
                content_parts.append("=" * 60)
                content_parts.append("2. NUKTA MUHIMU / KEY POINTS")
                content_parts.append("=" * 60)
                for kp in key_points:
                    content_parts.append(f"  • {kp}")
                content_parts.append("")
            
            # Teaching methods
            tm = note_data.get('teaching_methods', '')
            if tm:
                content_parts.append("=" * 60)
                content_parts.append("3. MBINU ZA UFUNDISHAJI / TEACHING METHODS")
                content_parts.append("=" * 60)
                content_parts.append(tm)
                content_parts.append("")
            
            # Quiz
            quiz = note_data.get('quiz', [])
            if quiz:
                content_parts.append("=" * 60)
                content_parts.append("4. TATHMINI / ASSESSMENT — MASWALI NA MAJIBU")
                content_parts.append("=" * 60)
                for i, q in enumerate(quiz, 1):
                    content_parts.append(f"\nSwali {i}: {q.get('question', '')}")
                    content_parts.append(f"Jibu: {q.get('answer', '')}")
                content_parts.append("")
            
            # Conclusion
            conclusion = note_data.get('conclusion', '')
            if conclusion:
                content_parts.append("=" * 60)
                content_parts.append("5. MWONGOZO / CONCLUSION & RECOMMENDATIONS")
                content_parts.append("=" * 60)
                content_parts.append(conclusion)
                content_parts.append("")
            
            note_content = '\\n'.join(content_parts)'''

if old_response in py_content:
    py_content = py_content.replace(old_response, new_response, 1)
    print('✅ Backend response formatting updated to notebook style')
else:
    print('❌ Could not find the old response formatting in views.py')

# Also update the return to include note_data with all fields
old_return = '''            return JsonResponse({
                'success': True,
                'note_id': note.id,
                'note_data': note_data,
                'created': note.created_at.isoformat(),
            })'''

new_return = '''            return JsonResponse({
                'success': True,
                'note_id': note.id,
                'note_data': note_data,
                'note_html': note_content,
                'created': note.created_at.isoformat(),
            })'''

if old_return in py_content:
    py_content = py_content.replace(old_return, new_return, 1)
    print('✅ Backend return updated to include note_html')
else:
    print('❌ Could not find the old return in views.py')

# Write back views.py
with open('curriculum/views.py', 'w') as f:
    f.write(py_content)
print('✅ views.py updated')


# =============================================================================
# PART 2: Redesign lesson_notes.html
# =============================================================================
with open('curriculum/templates/curriculum/lesson_notes.html', 'r') as f:
    html = f.read()

new_html = '''{% extends 'curriculum/base.html' %}
{% block title %}Lesson Notes{% endblock %}
{% block extra_css %}
<style>
  /* ── Notebook-style generated notes ── */
  .notebook-page {
    background: linear-gradient(to bottom, #fffcf0, #fff9e6);
    border: 1px solid #e8dcc8;
    border-radius: var(--radius-md);
    padding: 2rem 2rem 2rem 3rem;
    position: relative;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06), inset 0 0 0 1px rgba(255,255,255,0.8);
    font-family: 'Georgia', 'Times New Roman', serif;
    line-height: 1.8;
  }
  .notebook-page::before {
    content: '';
    position: absolute;
    top: 0;
    left: 2rem;
    width: 1px;
    height: 100%;
    background: rgba(220, 80, 80, 0.15);
    box-shadow: 0 0 0 0.5px rgba(220, 80, 80, 0.08);
  }
  .notebook-page h2 {
    font-family: 'Georgia', serif;
    color: #1a3c2e;
    border-bottom: 2px solid #c9a84c;
    padding-bottom: 8px;
    margin-bottom: 1.25rem;
    font-size: 1.3rem;
  }
  .notebook-page h3 {
    font-family: 'Georgia', serif;
    color: #2d5a3e;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    font-size: 1.1rem;
  }
  .notebook-page .section-divider {
    border: none;
    border-top: 2px dashed #c9a84c;
    margin: 1.5rem 0;
  }
  .notebook-page p {
    margin-bottom: 1rem;
    text-align: justify;
    color: #2a2a2a;
  }
  .notebook-page ul {
    padding-left: 1.5rem;
    margin-bottom: 1rem;
  }
  .notebook-page ul li {
    margin-bottom: 0.5rem;
    list-style-type: '📌 ';
    padding-left: 0.5rem;
  }
  .notebook-page .quiz-item {
    background: rgba(201, 168, 76, 0.08);
    border-left: 3px solid var(--gold-400);
    padding: 0.85rem 1rem;
    margin-bottom: 0.75rem;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  }
  .notebook-page .quiz-item .question {
    font-weight: 700;
    color: #1a3c2e;
    margin-bottom: 4px;
  }
  .notebook-page .quiz-item .answer {
    color: #4a4a4a;
    padding-left: 1rem;
    border-left: 2px solid var(--green-500);
    margin-left: 0.5rem;
  }
  .notebook-page .conclusion-box {
    background: rgba(31, 122, 61, 0.04);
    border: 1px solid rgba(31, 122, 61, 0.15);
    border-radius: var(--radius-sm);
    padding: 1rem 1.25rem;
    margin-top: 1rem;
  }

  /* ── Generate section card ── */
  .generate-card {
    background: linear-gradient(135deg, #f8faf6 0%, #f0f5ed 100%);
    border: 1.5px solid var(--green-500);
    border-radius: var(--radius-md);
    padding: 1.5rem;
    position: relative;
    overflow: hidden;
  }
  .generate-card::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -30%;
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(31,122,61,0.04) 0%, transparent 70%);
    border-radius: 50%;
  }
  .generate-card .btn-generate {
    background: linear-gradient(135deg, var(--green-500), #166534);
    color: #fff;
    border: none;
    padding: 0.75rem 1.5rem;
    font-weight: 700;
    font-size: 0.95rem;
    border-radius: var(--radius-sm);
    transition: all 0.3s ease;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    justify-content: center;
  }
  .generate-card .btn-generate:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(31,122,61,0.3);
  }
  .generate-card .btn-generate:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }
  .generate-card select {
    width: 100%;
    padding: 0.65rem 0.85rem;
    border: 1.5px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    background: var(--bg-card-solid);
    color: var(--text-primary);
    transition: border-color 0.2s;
  }
  .generate-card select:focus {
    border-color: var(--green-500);
    outline: none;
    box-shadow: 0 0 0 3px rgba(31,122,61,0.1);
  }

  /* ── Notes list cards ── */
  .note-card-compact {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1rem;
    transition: all var(--duration-normal) var(--ease-out);
    cursor: pointer;
  }
  .note-card-compact:hover {
    border-color: var(--green-500);
    box-shadow: var(--shadow-sm);
  }
  .note-card-compact .note-title {
    font-weight: 700;
    font-size: var(--font-size-sm);
    color: var(--text-primary);
    margin-bottom: 2px;
  }
  .note-card-compact .note-meta {
    font-size: 10px;
    color: var(--text-muted);
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .note-card-compact .note-preview {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Status animation ── */
  .gen-status {
    font-size: var(--font-size-xs);
    padding: 0.4rem 0.75rem;
    border-radius: var(--radius-sm);
    margin-top: 0.5rem;
    display: none;
  }
  .gen-status.show { display: block; }
  .gen-status.info { background: rgba(31,122,61,0.06); color: var(--green-500); }
  .gen-status.error { background: rgba(220,38,38,0.06); color: var(--error); }
  .gen-status.success { background: rgba(31,122,61,0.08); color: var(--green-500); }

  /* ── View Note Modal ── */
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.5);
    z-index: 1000;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.show { display: flex; }
  .modal-content {
    background: var(--bg-card-solid);
    border-radius: var(--radius-md);
    padding: 1.5rem;
    max-width: 700px;
    width: 95%;
    max-height: 85vh;
    overflow-y: auto;
    position: relative;
    box-shadow: var(--shadow-lg);
  }
  .modal-close {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    background: none;
    border: none;
    font-size: 1.25rem;
    color: var(--text-muted);
    cursor: pointer;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: all 0.2s;
  }
  .modal-close:hover {
    background: rgba(0,0,0,0.05);
    color: var(--text-primary);
  }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid px-0">
  <!-- Header -->
  <div class="c-card p-3 mb-3" style="border-left:4px solid var(--gold-400);">
    <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
      <div class="stat-icon" style="background:var(--green-500);">
        <i class="fas fa-book-open" style="color:#fff;font-size:1.1rem;"></i>
      </div>
      <div style="flex:1;">
        <h4 style="font-family:var(--font-display);font-weight:800;color:var(--text-primary);margin:0;font-size:clamp(0.9rem,1.5vw,1.15rem);">
          📖 Lesson Notes — Daftari la Somo
        </h4>
        <p style="font-size:var(--font-size-xs);color:var(--text-secondary);margin:2px 0 0;">
          Tayarisha maelezo kamili ya somo kwa mtindo wa daftari — yenye muhtasari, nukta muhimu, na maswali ya tathmini
        </p>
      </div>
      {% if school_level %}
      <span class="chip {% if school_level == 'Primary' %}chip-green{% else %}chip-blue{% endif %}" style="font-size:9px;">
        <i class="fas fa-school"></i> {{ school_level }} School
      </span>
      {% endif %}
    </div>
  </div>

  <div class="row g-3">
    <!-- LEFT: Generate Notes -->
    <div class="col-lg-5 col-xl-4">
      <div class="generate-card">
        <div style="position:relative;z-index:1;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:0.75rem;">
            <div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--green-500),#166534);display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(31,122,61,0.2);">
              <i class="fas fa-wand-magic-sparkles" style="color:#fff;font-size:1.1rem;"></i>
            </div>
            <div>
              <h5 style="font-family:var(--font-display);font-weight:800;font-size:1rem;margin:0;color:var(--text-primary);">
                Generate Notes from Lesson Plan
              </h5>
              <p style="font-size:10px;color:var(--text-secondary);margin:2px 0 0;">
                Chagua lesson plan ili kuzalisha daftari kamili la somo + maswali ya tathmini
              </p>
            </div>
          </div>
          
          <form id="generateForm">
            {% csrf_token %}
            <div class="mb-2">
              <label style="font-size:11px;font-weight:600;color:var(--text-secondary);display:block;margin-bottom:4px;">
                <i class="fas fa-file-alt text-gold me-1"></i> Chagua Lesson Plan
              </label>
              <select id="lpSelect" required>
                <option value="">— Chagua Lesson Plan —</option>
                {% for lp in saved_lessons %}
                <option value="{{ lp.id }}">{{ lp.topic|truncatechars:50 }} — {{ lp.subject.name }} ({{ lp.class_name }})</option>
                {% endfor %}
              </select>
              {% if not saved_lessons %}
              <p style="font-size:10px;color:var(--text-muted);margin-top:4px;">
                <i class="fas fa-info-circle"></i> Hakuna Lesson Plans zilizohifadhiwa. Tengeneza Lesson Plan kwanza.
              </p>
              {% endif %}
            </div>
            
            <button type="submit" class="btn-generate" id="generateBtn">
              <i class="fas fa-wand-magic-sparkles"></i> Generate Notes
            </button>
            
            <div id="genStatus" class="gen-status"></div>
          </form>
        </div>
      </div>

      <!-- Saved Notes List -->
      <div class="c-card mt-3">
        <div class="c-card-head">
          <h5 style="font-family:var(--font-display);font-weight:700;font-size:var(--font-size-sm);margin:0;color:var(--text-primary);">
            <i class="fas fa-save text-gold me-1"></i> Notes Zilizohifadhiwa ({{ notes|length }})
          </h5>
        </div>
        <div class="c-card-body" style="padding:0.5rem 0.75rem 0.75rem;">
          {% if notes %}
          <div style="display:flex;flex-direction:column;gap:6px;">
            {% for note in notes %}
            <div class="note-card-compact" onclick="viewNote('{{ note.id }}')">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div class="note-title">{{ note.topic|default:note.subject|truncatechars:40 }}</div>
                <div style="display:flex;gap:3px;">
                  <button class="btn-tlm btn-sm-tlm" style="background:rgba(220,38,38,0.06);color:var(--error);padding:2px 6px;font-size:9px;" onclick="event.stopPropagation(); deleteNote('{{ note.id }}')" title="Futa">
                    <i class="fas fa-trash-alt"></i>
                  </button>
                </div>
              </div>
              <div class="note-meta">
                <span><i class="fas fa-book"></i> {{ note.subject|default:"—" }}</span>
                <span><i class="fas fa-users"></i> {{ note.class_name|default:"—" }}</span>
                <span><i class="far fa-clock"></i> {{ note.created_at|date:"d M Y" }}</span>
              </div>
              <div class="note-preview">{{ note.content|truncatechars:100 }}</div>
            </div>
            {% endfor %}
          </div>
          {% else %}
          <div class="text-center py-4">
            <div style="width:44px;height:44px;background:rgba(31,122,61,0.06);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 0.5rem;">
              <i class="fas fa-book-open" style="font-size:1.1rem;color:var(--text-muted);"></i>
            </div>
            <p style="font-size:var(--font-size-xs);color:var(--text-muted);margin:0;">
              Hakuna notes zilizohifadhiwa bado.<br>Tumia "Generate Notes" kuunda notes zako.
            </p>
          </div>
          {% endif %}
        </div>
      </div>
    </div>

    <!-- RIGHT: Generated Notes Display -->
    <div class="col-lg-7 col-xl-8">
      <div id="notebookContainer" style="display:none;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;flex-wrap:wrap;gap:8px;">
          <h5 style="font-family:var(--font-display);font-weight:700;font-size:var(--font-size-sm);margin:0;color:var(--text-primary);">
            <i class="fas fa-book text-gold me-1"></i> Daftari la Somo
          </h5>
          <div style="display:flex;gap:6px;">
            <button class="btn-tlm btn-gold-tlm btn-sm-tlm" id="saveNotebookBtn">
              <i class="fas fa-save me-1"></i> Hifadhi Notes
            </button>
            <button class="btn-tlm btn-primary-tlm btn-sm-tlm" id="printNotebookBtn">
              <i class="fas fa-print me-1"></i> Chapisha
            </button>
          </div>
        </div>
        <div class="notebook-page" id="notebookContent"></div>
      </div>

      <div id="emptyState">
        <div class="c-card text-center py-5">
          <div style="width:70px;height:70px;background:rgba(31,122,61,0.06);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 0.75rem;">
            <i class="fas fa-book-open" style="font-size:2rem;color:var(--text-muted);"></i>
          </div>
          <h5 style="color:var(--text-secondary);font-weight:700;font-size:1rem;">Daftari la Somo</h5>
          <p style="color:var(--text-muted);font-size:var(--font-size-sm);max-width:400px;margin:0 auto;">
            Chagua lesson plan upande wa kushoto kisha bonyeza <strong>"Generate Notes"</strong> 
            ili kupata muhtasari kamili wa somo lenye maelezo ya kina, nukta muhimu, na maswali ya tathmini.
          </p>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- View Note Modal -->
<div class="modal-overlay" id="viewNoteModal">
  <div class="modal-content">
    <button class="modal-close" onclick="document.getElementById('viewNoteModal').classList.remove('show')">&times;</button>
    <div id="viewNoteContent"></div>
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
document.addEventListener('DOMContentLoaded', function() {
  const generateForm = document.getElementById('generateForm');
  const lpSelect = document.getElementById('lpSelect');
  const generateBtn = document.getElementById('generateBtn');
  const genStatus = document.getElementById('genStatus');
  const notebookContainer = document.getElementById('notebookContainer');
  const notebookContent = document.getElementById('notebookContent');
  const emptyState = document.getElementById('emptyState');
  const saveNotebookBtn = document.getElementById('saveNotebookBtn');

  let lastGeneratedData = null;
  let lastGeneratedHtml = null;

  // ── Generate Notes from Lesson Plan ──
  generateForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const lpId = lpSelect.value;
    
    if (!lpId) {
      genStatus.textContent = '❌ Tafadhali chagua Lesson Plan kwanza';
      genStatus.className = 'gen-status show error';
      return;
    }

    generateBtn.disabled = true;
    generateBtn.innerHTML = '<div class="spinner-tlm" style="width:18px;height:18px;border-width:2px;border-color:rgba(255,255,255,0.3) transparent rgba(255,255,255,0.3) rgba(255,255,255,0.3);"></div> Inazalisha Daftari...';
    genStatus.textContent = '⏳ AI inatayarisha daftari kamili la somo... Hii inaweza kuchukua sekunde 15-30.';
    genStatus.className = 'gen-status show info';

    fetch('{% url "curriculum:generate_lesson_note_from_lp" %}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': '{{ csrf_token }}'
      },
      body: JSON.stringify({ lesson_plan_id: lpId }),
    })
    .then(r => r.json())
    .then(data => {
      generateBtn.disabled = false;
      generateBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Generate Notes';
      
      if (data.success) {
        const noteData = data.note_data;
        lastGeneratedData = noteData;
        lastGeneratedHtml = data.note_html || '';
        
        // Build beautiful notebook display
        let html = '';
        
        // Title
        html += `<h2>📖 ${noteData.title || 'Lesson Notes'}</h2>`;
        
        // Summary paragraphs
        const paragraphs = noteData.summary_paragraphs || [];
        if (paragraphs.length > 0) {
          html += '<h3>📝 Muhtasari / Summary</h3>';
          paragraphs.forEach(function(p) {
            if (p.trim()) html += `<p>${p.trim()}</p>`;
          });
        }
        
        html += '<hr class="section-divider">';
        
        // Key points
        const keyPoints = noteData.key_points || [];
        if (keyPoints.length > 0) {
          html += '<h3>📍 Nukta Muhimu / Key Points</h3><ul>';
          keyPoints.forEach(function(kp) {
            if (kp.trim()) html += `<li>${kp.trim()}</li>`;
          });
          html += '</ul>';
          html += '<hr class="section-divider">';
        }
        
        // Teaching methods
        const tm = noteData.teaching_methods || '';
        if (tm.trim()) {
          html += '<h3>🎯 Mbinu za Ufundishaji / Teaching Methods</h3>';
          html += `<p>${tm.trim()}</p>`;
          html += '<hr class="section-divider">';
        }
        
        // Quiz
        const quiz = noteData.quiz || [];
        if (quiz.length > 0) {
          html += '<h3>❓ Tathmini / Assessment — Maswali na Majibu</h3>';
          quiz.forEach(function(q, i) {
            if (q.question || q.answer) {
              html += '<div class="quiz-item">';
              html += `<div class="question">Swali ${i+1}: ${q.question || ''}</div>`;
              html += `<div class="answer"><strong>Jibu:</strong> ${q.answer || ''}</div>`;
              html += '</div>';
            }
          });
          html += '<hr class="section-divider">';
        }
        
        // Conclusion
        const conclusion = noteData.conclusion || '';
        if (conclusion.trim()) {
          html += '<h3>💡 Mwongozo / Conclusion & Recommendations</h3>';
          html += `<div class="conclusion-box"><p style="margin:0;">${conclusion.trim()}</p></div>`;
        }
        
        notebookContent.innerHTML = html;
        notebookContainer.style.display = 'block';
        emptyState.style.display = 'none';
        
        genStatus.textContent = '✅ Daftari limezalishwa kikamilifu! Bonyeza "Hifadhi Notes" kuhifadhi.';
        genStatus.className = 'gen-status show success';
        
        // Auto-scroll to notebook
        notebookContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        genStatus.textContent = '❌ ' + (data.error || 'Hitilafu wakati wa kuzalisha. Jaribu tena.');
        genStatus.className = 'gen-status show error';
      }
    })
    .catch(err => {
      generateBtn.disabled = false;
      generateBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Generate Notes';
      genStatus.textContent = '❌ Network error: ' + err.message;
      genStatus.className = 'gen-status show error';
    });
  });

  // ── Save Notebook ──
  saveNotebookBtn.addEventListener('click', function() {
    if (!lastGeneratedHtml) {
      showToast('Hakuna daftari la kuhifadhi. Generate Notes kwanza.', 'warning');
      return;
    }
    
    const btn = this;
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner-tlm" style="width:14px;height:14px;border-width:2px;"></div> Inahifadhi...';
    
    // Get info from the selected lesson plan
    const selectedOption = lpSelect.options[lpSelect.selectedIndex];
    const lpInfo = selectedOption ? selectedOption.text : '';
    
    // Extract subject, class, topic from the selected lesson plan
    const fd = {
      note_id: null,
      content: lastGeneratedHtml,
      subject: '{{ teacher_subject_name|escapejs }}',
      class_name: '',
      topic: lastGeneratedData ? (lastGeneratedData.title || 'Lesson Notes') : 'Lesson Notes',
      education_level: '{{ teacher_edu_level }}',
    };
    
    fetch('{% url "curriculum:save_lesson_note" %}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': '{{ csrf_token }}'
      },
      body: JSON.stringify({
        note_id: null,
        content: lastGeneratedHtml,
        subject: lastGeneratedData && lastGeneratedData.title ? lastGeneratedData.title.split('—')[0].trim() : '{{ teacher_subject_name|escapejs }}',
        class_name: '{{ teacher_class_name|escapejs }}',
        topic: (lastGeneratedData && lastGeneratedData.title) || 'Lesson Notes',
        education_level: '{{ teacher_edu_level }}',
      }),
    })
    .then(r => r.json())
    .then(data => {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-save me-1"></i> Hifadhi Notes';
      if (data.success) {
        showToast('✅ Daftari limehifadhiwa!', 'success');
        setTimeout(() => location.reload(), 1200);
      } else {
        showToast('❌ ' + (data.error || 'Hitilafu'), 'error');
      }
    })
    .catch(err => {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-save me-1"></i> Hifadhi Notes';
      showToast('❌ Network error', 'error');
    });
  });

  // ── Print Notebook ──
  document.getElementById('printNotebookBtn').addEventListener('click', function() {
    const content = document.getElementById('notebookContent').innerHTML;
    if (!content) return;
    const win = window.open('', '', 'width=800,height=600');
    win.document.write('<html><head><title>Daftari la Somo</title>');
    win.document.write('<style>body{font-family:Georgia,serif;padding:2rem;line-height:1.8;max-width:700px;margin:auto;}' +
      'h2{border-bottom:2px solid #c9a84c;padding-bottom:8px;}' +
      'h3{color:#2d5a3e;margin-top:1.5rem;}.quiz-item{border-left:3px solid #c9a84c;padding:0.5rem 1rem;margin-bottom:1rem;}' +
      '.quiz-item .question{font-weight:700;}.quiz-item .answer{padding-left:1rem;border-left:2px solid #1f7a3d;margin-left:0.5rem;}' +
      '.conclusion-box{border:1px solid #1f7a3d;padding:1rem;}.section-divider{border-top:2px dashed #c9a84c;}ul li{margin-bottom:0.5rem;}' +
      '</style></head><body>');
    win.document.write(content);
    win.document.write('</body></html>');
    win.document.close();
    win.print();
  });
});

// ── View saved note ──
function viewNote(noteId) {
  fetch('{% url "curriculum:get_lesson_note" 0 %}'.replace('/0/', '/' + noteId + '/'))
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const note = data.note;
        const modal = document.getElementById('viewNoteModal');
        
        // Convert stored content to beautiful display
        let content = note.content;
        
        // If it looks like plain text (not HTML), wrap it
        if (!content.includes('<')) {
          content = content.replace(/\\n/g, '<br>');
          content = '<div style="white-space:pre-wrap;font-family:Georgia,serif;line-height:1.8;">' + content + '</div>';
        }
        
        document.getElementById('viewNoteContent').innerHTML = content;
        modal.classList.add('show');
      } else {
        showToast('❌ ' + (data.error || 'Note haipatikani'), 'error');
      }
    })
    .catch(() => showToast('❌ Hitilafu kupakia note', 'error'));
}

// ── Delete note ──
function deleteNote(noteId) {
  if (!confirm('Una uhakika unataka kufuta note hii?')) return;
  fetch('{% url "curriculum:delete_lesson_note" %}', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': '{{ csrf_token }}'
    },
    body: JSON.stringify({ note_id: noteId }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      showToast('✅ Note imefutwa!', 'info');
      setTimeout(() => location.reload(), 500);
    } else {
      showToast('❌ ' + (data.error || 'Imeshindwa kufuta'), 'error');
    }
  });
}
</script>
{% endblock %}
'''

# Write the new HTML
with open('curriculum/templates/curriculum/lesson_notes.html', 'w') as f:
    f.write(new_html)
print('✅ lesson_notes.html completely redesigned with beautiful UI')

print('\n🎉 All changes applied!')
