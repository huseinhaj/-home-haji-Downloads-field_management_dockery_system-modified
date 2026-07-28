""""
Management command to seed the TIE (Tanzania Institute of Education) syllabus
topics and subtopics into the database.

Usage:
    python manage.py seed_tie_syllabus          # Seed all data
    python manage.py seed_tie_syllabus --form 1 # Seed only Form 1
    python manage.py seed_tie_syllabus --subject mathematics  # Seed only one subject
    python manage.py seed_tie_syllabus --list-subjects  # List available subjects
    python manage.py seed_tie_syllabus --check     # Check what's already seeded

Data source: Official TIE Syllabus for Ordinary Secondary Education (Form I-IV)
Based on the 2023 Competence-Based Curriculum.
"""
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from field_app.models import Subject
from curriculum.models import SubjectTopic, TopicSubtopic

# =============================================================================
# FORM 1 TOPICS & SUBTOPICS — TIE Official Syllabus
# =============================================================================

FORM_1_SYLLABUS = {
    "Mathematics": {
        "subject_code": "secondary",  # Subject level
        "topics": [
            {
                "name": "Concept of Mathematics",
                "order": 1,
                "subtopics": [
                    "Meaning of Mathematics",
                    "Branches of Mathematics",
                    "Relationship between Mathematics and other subjects",
                    "Importance of Mathematics",
                ]
            },
            {
                "name": "Numbers",
                "order": 2,
                "subtopics": [
                    "Concept of numbers",
                    "Rational numbers",
                    "Irrational numbers",
                    "Real numbers",
                    "Inequalities in real numbers",
                    "Absolute value of a real number",
                ]
            },
            {
                "name": "Approximations",
                "order": 3,
                "subtopics": [
                    "Meaning of approximations",
                    "Rounding off numbers",
                    "Significant figures",
                    "Approximations in calculations",
                ]
            },
            {
                "name": "Ratios and Proportions",
                "order": 4,
                "subtopics": [
                    "Ratios",
                    "Proportions",
                ]
            },
            {
                "name": "Algebra",
                "order": 5,
                "subtopics": [
                    "Algebraic expressions",
                    "Algebraic equations",
                    "Linear simultaneous equations",
                    "Solution of inequalities with one unknown",
                ]
            },
            {
                "name": "Coordinate Geometry",
                "order": 6,
                "subtopics": [
                    "Basic concepts of coordinate geometry",
                    "Gradient of a straight line",
                    "Equation of a straight line",
                    "General equation of a straight line",
                    "Graphing linear equations",
                    "Solving linear simultaneous equations graphically",
                ]
            },
        ]
    },
    "English": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Listening to Simple Texts",
                "order": 1,
                "subtopics": [
                    "Understanding spoken English",
                    "Listening for specific information",
                    "Following instructions and directions",
                    "Listening to speeches and interviews",
                    "Listening to radio programmes",
                ]
            },
            {
                "name": "Giving Directions",
                "order": 2,
                "subtopics": [
                    "Using imperative forms",
                    "Directional vocabulary",
                    "Understanding landmarks and maps",
                    "Describing locations",
                ]
            },
            {
                "name": "Using a Dictionary",
                "order": 3,
                "subtopics": [
                    "Alphabetical order",
                    "Parts of speech identification",
                    "Phonetic transcription",
                    "Meaning of words",
                    "Synonyms and antonyms",
                ]
            },
            {
                "name": "Daily Routines",
                "order": 4,
                "subtopics": [
                    "Describing habits",
                    "Telling time",
                    "Using frequency adverbs",
                    "Present simple tense",
                ]
            },
            {
                "name": "Describing Ongoing Activities",
                "order": 5,
                "subtopics": [
                    "Present continuous tense",
                    "Narrating actions happening now",
                    "Describing scenes and events",
                ]
            },
            {
                "name": "Likes and Dislikes",
                "order": 6,
                "subtopics": [
                    "Expressing preferences",
                    "Talking about interests and hobbies",
                    "Agreeing and disagreeing",
                ]
            },
            {
                "name": "Family Tree",
                "order": 7,
                "subtopics": [
                    "Family relationship vocabulary",
                    "Describing family structures",
                    "Family roles and responsibilities",
                ]
            },
            {
                "name": "Expressing Opinions and Feelings",
                "order": 8,
                "subtopics": [
                    "Stating views and opinions",
                    "Emotional expression",
                    "Agreeing and disagreeing politely",
                ]
            },
            {
                "name": "Expressing Past Events",
                "order": 9,
                "subtopics": [
                    "Past simple tense",
                    "Narrating completed actions",
                    "Talking about personal experiences",
                ]
            },
            {
                "name": "Expressing Future Plans",
                "order": 10,
                "subtopics": [
                    "Using 'going to' for future",
                    "Using 'will' for future",
                    "Discussing intentions and future events",
                ]
            },
            {
                "name": "Intensive Reading",
                "order": 11,
                "subtopics": [
                    "Reading for detail",
                    "Understanding main ideas",
                    "Critical thinking from texts",
                ]
            },
            {
                "name": "Reading Literary Works",
                "order": 12,
                "subtopics": [
                    "Introduction to stories",
                    "Introduction to poems",
                    "Basic literary appreciation",
                ]
            },
            {
                "name": "Media Information",
                "order": 13,
                "subtopics": [
                    "Understanding newspaper articles",
                    "Understanding advertisements",
                    "Understanding digital content",
                ]
            },
            {
                "name": "Friendly Letters",
                "order": 14,
                "subtopics": [
                    "Format of informal letters",
                    "Structure of friendly letters",
                    "Language skills for correspondence",
                ]
            },
            {
                "name": "Taking Notes",
                "order": 15,
                "subtopics": [
                    "Listening for gist",
                    "Reading for gist",
                    "Extracting key points",
                    "Summarizing information",
                ]
            },
            {
                "name": "Forms and Diaries",
                "order": 16,
                "subtopics": [
                    "Understanding formal documents",
                    "Filling in forms",
                    "Personal record-keeping",
                ]
            },
        ]
    },
    "Kiswahili": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Lugha na Mawasiliano",
                "order": 1,
                "subtopics": [
                    "Dhana ya lugha",
                    "Dhana ya mawasiliano",
                    "Dhana ya lugha ya Kiswahili",
                    "Umuhimu wa kujifunza Kiswahili",
                    "Matamshi na lafudhi ya Kiswahili",
                    "Kiimbo",
                    "Silabi",
                ]
            },
            {
                "name": "Aina za Maneno",
                "order": 2,
                "subtopics": [
                    "Dhana ya aina za maneno",
                    "Nomino (Nouns)",
                    "Viwakilishi (Pronouns)",
                    "Vivumishi (Adjectives)",
                    "Vitenzi (Verbs)",
                    "Vielezi (Adverbs)",
                    "Viunganishi (Conjunctions)",
                    "Vihusishi (Prepositions)",
                    "Vihisishi (Interjections)",
                    "Matumizi ya kamusi",
                ]
            },
            {
                "name": "Fasihi kwa Ujumla",
                "order": 3,
                "subtopics": [
                    "Fasihi na dhima zake",
                    "Aina za fasihi",
                    "Tanzu za fasihi simulizi na vipera vyake",
                    "Usimulizi wa hadithi",
                    "Uhakiki wa kazi za fasihi simulizi",
                ]
            },
            {
                "name": "Uandishi wa Insha na Barua",
                "order": 4,
                "subtopics": [
                    "Kuandika insha za wasifu",
                    "Kuandika barua ya kirafiki",
                ]
            },
            {
                "name": "Ufahamu",
                "order": 5,
                "subtopics": [
                    "Dhana ya ufahamu",
                    "Ufahamu wa kuona",
                    "Ufahamu wa kusikiliza",
                    "Ufahamu wa kusoma",
                    "Kusoma kwa burudani",
                    "Ufupisho",
                ]
            },
        ]
    },
    "Biology": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Introduction to Biology",
                "order": 1,
                "subtopics": [
                    "Meaning of Biology",
                    "Branches of Biology",
                    "Importance of Biology",
                    "Relationship between Biology and other subjects",
                    "Career opportunities in Biology",
                ]
            },
            {
                "name": "Biology Laboratory",
                "order": 2,
                "subtopics": [
                    "Meaning of a Biology laboratory",
                    "Rules and safety in a Biology laboratory",
                    "Biology laboratory equipment",
                    "Handling and using Biology laboratory equipment",
                ]
            },
            {
                "name": "Scientific Processes in Biology",
                "order": 3,
                "subtopics": [
                    "Scientific procedures",
                    "Scientific skills",
                    "Observation and recording",
                    "Experimentation in Biology",
                ]
            },
            {
                "name": "First Aid and Safety in Our Environment",
                "order": 4,
                "subtopics": [
                    "Meaning of first aid",
                    "First aid kit and its contents",
                    "Common accidents and their first aid",
                    "Safety measures in the environment",
                ]
            },
            {
                "name": "Waste Disposal",
                "order": 5,
                "subtopics": [
                    "Meaning of waste",
                    "Types of waste",
                    "Effects of poor waste disposal",
                    "Methods of waste disposal",
                ]
            },
            {
                "name": "Personal Hygiene and Good Manners",
                "order": 6,
                "subtopics": [
                    "Meaning of personal hygiene",
                    "Types of personal hygiene",
                    "Importance of personal hygiene",
                    "Good manners and behaviour",
                ]
            },
            {
                "name": "Health, Immunity and Diseases",
                "order": 7,
                "subtopics": [
                    "Meaning of health",
                    "Types of diseases",
                    "Causes and transmission of diseases",
                    "Immunity and immunization",
                    "Prevention and control of diseases",
                ]
            },
            {
                "name": "STIs, STDs, HIV and AIDS",
                "order": 8,
                "subtopics": [
                    "Meaning of STIs, STDs, HIV and AIDS",
                    "Causes and transmission",
                    "Signs and symptoms",
                    "Prevention and control",
                    "Care and support for people living with HIV/AIDS",
                ]
            },
            {
                "name": "Cell Structure and Organization",
                "order": 9,
                "subtopics": [
                    "Meaning of a cell",
                    "Cell structures and functions",
                    "Differences between plant and animal cells",
                    "Cell organization (tissues, organs, systems)",
                ]
            },
            {
                "name": "Classification of Living Things",
                "order": 10,
                "subtopics": [
                    "Need for classification",
                    "Kingdoms of living things",
                    "Binomial nomenclature",
                    "Characteristics of each kingdom",
                ]
            },
            {
                "name": "Viruses, Kingdom Monera and Kingdom Protoctista",
                "order": 11,
                "subtopics": [
                    "Characteristics of viruses",
                    "Characteristics of Kingdom Monera",
                    "Characteristics of Kingdom Protoctista",
                    "Economic importance of each group",
                ]
            },
        ]
    },
    "History": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Meaning, Importance and Sources of History",
                "order": 1,
                "subtopics": [
                    "Meaning of History",
                    "Importance of studying History",
                    "Sources of historical information",
                    "Historical sites in Tanzania",
                    "Challenges of studying History",
                ]
            },
            {
                "name": "Human Evolution, Technology and Environment",
                "order": 2,
                "subtopics": [
                    "Theories of human origin",
                    "Stages of human evolution",
                    "Early tool making and technology",
                    "Impact of environment on human development",
                ]
            },
            {
                "name": "Development of Agriculture in Pre-colonial African Societies",
                "order": 3,
                "subtopics": [
                    "Meaning of agriculture",
                    "Origin and development of agriculture in Africa",
                    "Types of agriculture in pre-colonial Africa",
                    "Effects of agricultural development",
                ]
            },
            {
                "name": "Handicraft and Mining Industries in Pre-colonial Africa",
                "order": 4,
                "subtopics": [
                    "Handicraft industries in pre-colonial Africa",
                    "Mining industries in pre-colonial Africa",
                    "Iron working technology",
                    "Organization of production",
                ]
            },
            {
                "name": "Trade in Pre-colonial Africa",
                "order": 5,
                "subtopics": [
                    "Meaning and types of trade",
                    "Local trade systems",
                    "Regional trade systems",
                    "Long-distance trade",
                    "Effects of trade",
                ]
            },
            {
                "name": "Development of Social and Political Systems in Pre-colonial Africa",
                "order": 6,
                "subtopics": [
                    "Clan and kinship systems",
                    "Age-set systems",
                    "State formation in pre-colonial Africa",
                    "Societal organization and leadership",
                ]
            },
        ]
    },
    "Geography": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "The Concept of Geography",
                "order": 1,
                "subtopics": [
                    "Meaning of Geography",
                    "Branches of Geography",
                    "Interrelationship between geographical phenomena",
                    "Importance of studying Geography",
                ]
            },
            {
                "name": "The Solar System",
                "order": 2,
                "subtopics": [
                    "Concept of the solar system",
                    "Components of the solar system",
                    "The sun and solar energy",
                    "Planets and their characteristics",
                    "Other bodies in the solar system",
                    "The earth (size, shape, evidence of sphericity)",
                    "The earth's movement (rotation and revolution)",
                    "Latitudes and longitudes",
                    "Time zones and the International Date Line",
                ]
            },
            {
                "name": "Major Features of the Earth's Surface",
                "order": 3,
                "subtopics": [
                    "The earth's surface",
                    "Continents and their features",
                    "Water bodies",
                    "The ocean floor and its features",
                    "Major relief features",
                ]
            },
            {
                "name": "Weather and Climate",
                "order": 4,
                "subtopics": [
                    "Meaning of weather",
                    "Importance of weather",
                    "Elements of weather",
                    "Measuring and recording weather",
                    "Weather instruments and stations",
                    "Basic concepts of climate",
                ]
            },
            {
                "name": "Map Work",
                "order": 5,
                "subtopics": [
                    "The concept of a map",
                    "Components of a map",
                    "Measuring distance on maps",
                    "Calculating area on maps",
                    "Locating positions on maps",
                    "Uses of maps",
                ]
            },
        ]
    },
    "Civics": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Introduction to Civics",
                "order": 1,
                "subtopics": [
                    "Meaning of Civics",
                    "Main themes addressed in Civics",
                    "Relationship between Civics and other subjects",
                    "Importance of studying Civics",
                ]
            },
            {
                "name": "Our Nation",
                "order": 2,
                "subtopics": [
                    "Meaning of a nation",
                    "Components of our nation",
                    "National symbols",
                    "National festivals",
                    "Significance of national festivals",
                ]
            },
            {
                "name": "Promotion of Life Skills",
                "order": 3,
                "subtopics": [
                    "Meaning of life skills",
                    "Types of life skills",
                    "Effective decision-making skills",
                    "Importance of life skills",
                    "Consequences of not using life skills",
                ]
            },
            {
                "name": "Human Rights",
                "order": 4,
                "subtopics": [
                    "Meaning of human rights",
                    "Universal Declaration of Human Rights",
                    "Types and categories of human rights",
                    "Importance of human rights",
                    "Role of government and NGOs in promoting human rights",
                    "Human rights abuse and ways to combat it",
                ]
            },
            {
                "name": "Responsible Citizenship",
                "order": 5,
                "subtopics": [
                    "Meaning of citizen and citizenship",
                    "Types and privileges of citizenship",
                    "Conditions for losing citizenship",
                    "Civic responsibilities",
                    "Special groups and responsibilities toward them",
                ]
            },
            {
                "name": "Career and Work-Related Activities",
                "order": 6,
                "subtopics": [
                    "Meaning of career",
                    "Factors affecting career development",
                    "Types of work-related activities",
                    "Choosing a career",
                    "Importance of work",
                ]
            },
            {
                "name": "Family Life Education",
                "order": 7,
                "subtopics": [
                    "Concept and types of families",
                    "Importance of a family",
                    "Factors contributing to family stability",
                    "Responsibilities of family members",
                    "Consequences of not fulfilling family responsibilities",
                ]
            },
            {
                "name": "Proper Behaviour and Decision Making",
                "order": 8,
                "subtopics": [
                    "Meaning and types of behaviour",
                    "Factors influencing behaviour",
                    "Indicators of proper and improper behaviours",
                    "Importance of behaving properly",
                    "Rational decision-making steps",
                    "Ways to avoid irrational decisions",
                ]
            },
            {
                "name": "Road Safety Education",
                "order": 9,
                "subtopics": [
                    "Meaning of road safety education",
                    "Road signs and their interpretation",
                    "Consequences of not obeying road signs",
                    "Causes and effects of road accidents",
                    "Prevention of road accidents",
                ]
            },
        ]
    },
    "Physics": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Introduction to Physics",
                "order": 1,
                "subtopics": [
                    "Meaning of Physics",
                    "Branches of Physics",
                    "Relationship between Physics and other subjects",
                    "Importance of Physics in daily life",
                    "Career opportunities in Physics",
                ]
            },
            {
                "name": "Laboratory Techniques and Safety",
                "order": 2,
                "subtopics": [
                    "Physics laboratory rules and regulations",
                    "Physics laboratory equipment",
                    "Handling and storing equipment",
                    "First aid in the Physics laboratory",
                ]
            },
            {
                "name": "Measurements",
                "order": 3,
                "subtopics": [
                    "Concept of measurement",
                    "Basic quantities and SI units",
                    "Derived quantities and units",
                    "Measuring instruments",
                    "Accuracy and precision",
                    "Errors in measurement",
                ]
            },
            {
                "name": "Forces",
                "order": 4,
                "subtopics": [
                    "Meaning of force",
                    "Types of forces",
                    "Effects of forces",
                    "Measurement of forces",
                    "Scalar and vector quantities",
                ]
            },
            {
                "name": "Archimedes' Principle and Law of Floatation",
                "order": 5,
                "subtopics": [
                    "Concept of upthrust",
                    "Archimedes' Principle",
                    "Law of floatation",
                    "Applications of Archimedes' Principle",
                ]
            },
            {
                "name": "Structure and Properties of Matter",
                "order": 6,
                "subtopics": [
                    "States of matter",
                    "Kinetic theory of matter",
                    "Elasticity",
                    "Surface tension",
                    "Adhesion and cohesion",
                ]
            },
            {
                "name": "Pressure",
                "order": 7,
                "subtopics": [
                    "Concept of pressure",
                    "Pressure in solids",
                    "Pressure in liquids",
                    "Pressure in gases (atmospheric pressure)",
                    "Applications of pressure",
                ]
            },
            {
                "name": "Work, Energy and Power",
                "order": 8,
                "subtopics": [
                    "Concept of work",
                    "Concept of energy",
                    "Types and forms of energy",
                    "Concept of power",
                    "Law of conservation of energy",
                ]
            },
            {
                "name": "Light",
                "order": 9,
                "subtopics": [
                    "Concept of light",
                    "Sources of light",
                    "Rectilinear propagation of light",
                    "Formation of shadows",
                    "Reflection of light",
                    "Refraction of light",
                ]
            },
        ]
    },
    "Chemistry": {
        "subject_code": "secondary",
        "topics": [
            {
                "name": "Introduction to Chemistry",
                "order": 1,
                "subtopics": [
                    "Meaning of Chemistry",
                    "Branches of Chemistry",
                    "Relationship between Chemistry and other subjects",
                    "Importance of Chemistry in daily life",
                    "Career opportunities in Chemistry",
                ]
            },
            {
                "name": "Laboratory Techniques and Safety",
                "order": 2,
                "subtopics": [
                    "Chemistry laboratory rules",
                    "Chemistry laboratory apparatus",
                    "Handling chemicals safely",
                    "First aid in the Chemistry laboratory",
                ]
            },
            {
                "name": "Matter",
                "order": 3,
                "subtopics": [
                    "Concept of matter",
                    "States of matter",
                    "Classification of matter",
                    "Physical and chemical properties of matter",
                    "Changes of state",
                ]
            },
            {
                "name": "Elements and Symbols",
                "order": 4,
                "subtopics": [
                    "Concept of an element",
                    "Names and symbols of common elements",
                    "Classification of elements",
                ]
            },
            {
                "name": "Compounds and Mixtures",
                "order": 5,
                "subtopics": [
                    "Concept of a compound",
                    "Concept of a mixture",
                    "Differences between compounds and mixtures",
                    "Separation techniques for mixtures",
                ]
            },
            {
                "name": "Air Combustion and Rusting",
                "order": 6,
                "subtopics": [
                    "Composition of air",
                    "Concept of combustion",
                    "Conditions for combustion",
                    "Concept of rusting",
                    "Conditions for rusting",
                    "Methods of preventing rusting",
                ]
            },
            {
                "name": "Water and Solutions",
                "order": 7,
                "subtopics": [
                    "Concept of water",
                    "Sources of water",
                    "Properties of water",
                    "Concept of solutions",
                    "Types of solutions",
                    "Solubility and factors affecting it",
                ]
            },
            {
                "name": "Fuels and Energy",
                "order": 8,
                "subtopics": [
                    "Concept of fuels",
                    "Types of fuels",
                    "Uses of fuels",
                    "Environmental effects of fuel combustion",
                    "Alternative sources of energy",
                ]
            },
            {
                "name": "Atomic Structure",
                "order": 9,
                "subtopics": [
                    "Concept of an atom",
                    "Structure of an atom",
                    "Subatomic particles",
                    "Atomic number and mass number",
                    "Isotopes",
                ]
            },
        ]
    },
}

FORM_1_CLASS = "Form 1"


class Command(BaseCommand):
    help = "Seed TIE syllabus topics and subtopics into the database"

    def add_arguments(self, parser):
        parser.add_argument('--form', type=str, help='Form level to seed (e.g., 1, 2, 3, 4)')
        parser.add_argument('--subject', type=str, help='Subject name to seed (case-insensitive)')
        parser.add_argument('--list-subjects', action='store_true', help='List available subjects in seed data')
        parser.add_argument('--check', action='store_true', help='Check what is already seeded')

    def handle(self, *args, **options):
        if options['list_subjects']:
            self.list_subjects()
            return

        if options['check']:
            self.check_seeded()
            return

        form = options.get('form')
        subject_name = options.get('subject')

        if form and form != '1':
            self.stdout.write(self.style.WARNING(
                f"⚠️ Only Form 1 data is available in this version. Forms 2-4 coming soon."
            ))
            return

        # Filter syllabus data
        syllabus_data = FORM_1_SYLLABUS
        
        if subject_name:
            matched = {}
            for name, data in syllabus_data.items():
                if subject_name.lower() in name.lower():
                    matched[name] = data
            if not matched:
                self.stdout.write(self.style.ERROR(
                    f"✗ Subject '{subject_name}' not found. Available: {', '.join(syllabus_data.keys())}"
                ))
                return
            syllabus_data = matched

        self.seed_data(syllabus_data, form or '1')

    def list_subjects(self):
        self.stdout.write("\n📚 Available subjects in seed data (Form 1):")
        for name in FORM_1_SYLLABUS.keys():
            topics_count = len(FORM_1_SYLLABUS[name]['topics'])
            self.stdout.write(f"  • {name} ({topics_count} topics)")

    def check_seeded(self):
        topics_count = SubjectTopic.objects.count()
        subtopics_count = TopicSubtopic.objects.count()
        
        self.stdout.write(f"\n📊 Current syllabus data in database:")
        self.stdout.write(f"  Total topics: {topics_count}")
        self.stdout.write(f"  Total subtopics: {subtopics_count}")
        
        if topics_count > 0:
            self.stdout.write("\n  By subject:")
            for topic in SubjectTopic.objects.values('subject__name', 'class_name').distinct().order_by('subject__name'):
                count = SubjectTopic.objects.filter(
                    subject__name=topic['subject__name'],
                    class_name=topic['class_name']
                ).count()
                self.stdout.write(f"    • {topic['subject__name']} {topic['class_name']}: {count} topics")

    @transaction.atomic
    def seed_data(self, syllabus_data, form_number):
        class_name = f"Form {form_number}"
        
        for subject_name, subject_data in syllabus_data.items():
            # Find the subject in the database
            subject = Subject.objects.filter(
                name__iexact=subject_name,
                level=subject_data['subject_code']
            ).first()
            
            if not subject:
                # Try broader match
                subject = Subject.objects.filter(
                    name__iexact=subject_name
                ).first()
            
            if not subject:
                # Try contains match (e.g., "English" matches "English Language")
                subject = Subject.objects.filter(
                    name__icontains=subject_name
                ).first()
            
            if not subject:
                # Try matching just the first word
                first_word = subject_name.split()[0]
                subject = Subject.objects.filter(
                    name__icontains=first_word
                ).first()
            
            if not subject:
                self.stdout.write(self.style.WARNING(
                    f"⚠️ Subject '{subject_name}' not found in database. Skipping."
                ))
                continue
            
            self.stdout.write(f"\n📘 {subject.name} - {class_name}")
            
            for topic_data in subject_data['topics']:
                # Create or update the topic
                topic, created = SubjectTopic.objects.update_or_create(
                    subject=subject,
                    class_name=class_name,
                    name=topic_data['name'],
                    defaults={'order': topic_data['order']}
                )
                
                status = "✅ Created" if created else "🔄 Updated"
                self.stdout.write(f"  {status}: {topic.name}")
                
                # Remove existing subtopics for this topic to avoid duplicates
                TopicSubtopic.objects.filter(topic=topic).delete()
                
                # Create subtopics
                for i, subtopic_name in enumerate(topic_data.get('subtopics', [])):
                    TopicSubtopic.objects.create(
                        topic=topic,
                        name=subtopic_name,
                        order=i + 1
                    )
                
                self.stdout.write(f"     Subtopics: {len(topic_data.get('subtopics', []))}")
        
        # Summary
        total_topics = SubjectTopic.objects.filter(class_name=class_name).count()
        total_subtopics = TopicSubtopic.objects.filter(
            topic__class_name=class_name
        ).count()
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Done! {class_name}: {total_topics} topics, {total_subtopics} subtopics seeded."
        ))
