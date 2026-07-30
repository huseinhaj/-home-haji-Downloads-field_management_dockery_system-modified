"""
Management command to seed English Medium Primary School subjects
with topics and subtopics.

Usage:
    python manage.py seed_primary_syllabus          # Seed all primary subjects
    python manage.py seed_primary_syllabus --subject Arithmetic  # Seed one subject
    python manage.py seed_primary_syllabus --list    # List subjects to seed
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from field_app.models import Subject
from curriculum.models import SubjectTopic, TopicSubtopic


PRIMARY_SYLLABUS = {
    "Arithmetic": {
        "code": "P11",
        "topics": [
            {
                "name": "Numbers and Numeration",
                "order": 1,
                "subtopics": [
                    "Counting numbers (1-100, 1-1000, 1-1,000,000)",
                    "Place value and face value",
                    "Odd and even numbers",
                    "Prime and composite numbers",
                    "Ordering and comparing numbers",
                    "Number patterns and sequences",
                ]
            },
            {
                "name": "Addition",
                "order": 2,
                "subtopics": [
                    "Addition of whole numbers (up to 6 digits)",
                    "Addition with regrouping / carrying",
                    "Addition word problems",
                    "Properties of addition",
                    "Mental addition strategies",
                ]
            },
            {
                "name": "Subtraction",
                "order": 3,
                "subtopics": [
                    "Subtraction of whole numbers (up to 6 digits)",
                    "Subtraction with borrowing / regrouping",
                    "Subtraction word problems",
                    "Checking subtraction with addition",
                    "Mental subtraction strategies",
                ]
            },
            {
                "name": "Multiplication",
                "order": 4,
                "subtopics": [
                    "Multiplication tables (1-12)",
                    "Multiplying by 1-digit numbers",
                    "Multiplying by 2-digit and 3-digit numbers",
                    "Multiplication word problems",
                    "Properties of multiplication",
                    "Mental multiplication strategies",
                ]
            },
            {
                "name": "Division",
                "order": 5,
                "subtopics": [
                    "Basic division facts",
                    "Division by 1-digit and 2-digit numbers",
                    "Division with remainders",
                    "Division word problems",
                    "Relationship between multiplication and division",
                ]
            },
            {
                "name": "Fractions",
                "order": 6,
                "subtopics": [
                    "Concept of fractions (halves, thirds, quarters)",
                    "Equivalent fractions",
                    "Comparing and ordering fractions",
                    "Addition and subtraction of fractions",
                    "Multiplication and division of fractions",
                    "Proper, improper and mixed fractions",
                ]
            },
            {
                "name": "Decimals",
                "order": 7,
                "subtopics": [
                    "Concept of decimals (tenths, hundredths, thousandths)",
                    "Comparing and ordering decimals",
                    "Addition and subtraction of decimals",
                    "Multiplication and division of decimals",
                    "Converting between fractions and decimals",
                    "Rounding decimals",
                ]
            },
            {
                "name": "Measurement",
                "order": 8,
                "subtopics": [
                    "Length (centimetres, metres, kilometres)",
                    "Mass (grams, kilograms, tonnes)",
                    "Capacity (millilitres, litres)",
                    "Perimeter and area",
                    "Volume of solids",
                    "Converting between units",
                ]
            },
            {
                "name": "Money",
                "order": 9,
                "subtopics": [
                    "Tanzania currency (coins and notes)",
                    "Adding and subtracting money",
                    "Shopping and change calculations",
                    "Profit and loss",
                    "Simple budgets and financial literacy",
                ]
            },
            {
                "name": "Time",
                "order": 10,
                "subtopics": [
                    "Reading clocks (analogue and digital)",
                    "Telling time (hours, half-hours, quarters, minutes)",
                    "AM and PM",
                    "Days, weeks, months, years",
                    "Elapsed time and duration",
                    "Calendar reading",
                ]
            },
            {
                "name": "Geometry",
                "order": 11,
                "subtopics": [
                    "Basic shapes (triangle, square, rectangle, circle)",
                    "Properties of 2D shapes",
                    "Properties of 3D shapes (cube, cuboid, cylinder, sphere)",
                    "Symmetry and patterns",
                    "Angles and lines",
                    "Position and direction",
                ]
            },
            {
                "name": "Data Handling and Statistics",
                "order": 12,
                "subtopics": [
                    "Collecting and organizing data",
                    "Tally marks and frequency tables",
                    "Pictographs and bar graphs",
                    "Line graphs and pie charts",
                    "Interpreting data (mean, median, mode)",
                    "Probability (certain, likely, unlikely, impossible)",
                ]
            },
        ]
    },
    "Culture": {
        "code": "P15",
        "topics": [
            {
                "name": "Our Nation Tanzania",
                "order": 1,
                "subtopics": [
                    "Meaning and importance of a nation",
                    "National symbols (flag, emblem, anthem)",
                    "National festivals and holidays",
                    "Unity and togetherness (Umoja na Mshikamano)",
                    "Respecting national leaders and elders",
                ]
            },
            {
                "name": "Customs and Traditions",
                "order": 2,
                "subtopics": [
                    "Meaning of culture and traditions",
                    "Customs of various Tanzanian ethnic groups",
                    "Traditional ceremonies and rituals",
                    "Traditional greetings and respect",
                    "Preserving Tanzanian culture",
                ]
            },
            {
                "name": "Social Institutions",
                "order": 3,
                "subtopics": [
                    "The family (nuclear and extended family)",
                    "Family roles and responsibilities",
                    "The community (neighbours, village, street)",
                    "Community leaders and their roles",
                    "Cooperation and helping others",
                ]
            },
            {
                "name": "Values and Ethics",
                "order": 4,
                "subtopics": [
                    "Good manners and behaviour (adabu)",
                    "Honesty and truthfulness",
                    "Responsibility and hard work",
                    "Respect for others and property",
                    "Religious and moral values",
                ]
            },
            {
                "name": "Art and Craft",
                "order": 5,
                "subtopics": [
                    "Traditional dances and music",
                    "Traditional musical instruments",
                    "Drawing and painting",
                    "Clay work and modelling",
                    "Weaving and beadwork",
                    "Role of art in culture",
                ]
            },
            {
                "name": "Food and Nutrition in Our Culture",
                "order": 6,
                "subtopics": [
                    "Traditional foods of Tanzania",
                    "Food preparation and preservation",
                    "Table manners and etiquette",
                    "Sharing food in the community",
                    "Food and cultural identity",
                ]
            },
        ]
    },
    "Health Care": {
        "code": "P16",
        "topics": [
            {
                "name": "Personal Hygiene",
                "order": 1,
                "subtopics": [
                    "Hand washing (before and after meals, after toilet)",
                    "Bathing and body cleanliness",
                    "Oral and dental hygiene (brushing teeth)",
                    "Hair and nail care",
                    "Clean clothes and uniforms",
                    "Using and maintaining a clean latrine/toilet",
                ]
            },
            {
                "name": "Nutrition and Balanced Diet",
                "order": 2,
                "subtopics": [
                    "Types of food (energy-giving, body-building, protective)",
                    "Food groups and their functions",
                    "A balanced diet",
                    "Vitamins and minerals",
                    "Malnutrition and its effects",
                    "Healthy eating habits",
                ]
            },
            {
                "name": "Common Diseases and Prevention",
                "order": 3,
                "subtopics": [
                    "Common communicable diseases (cold, flu, diarrhoea, malaria)",
                    "Causes and transmission of diseases",
                    "Signs and symptoms of common illnesses",
                    "Prevention and control of diseases",
                    "Vaccination and immunization",
                    "When to visit a health centre",
                ]
            },
            {
                "name": "Safety and First Aid",
                "order": 4,
                "subtopics": [
                    "Home and school safety rules",
                    "Road safety (crossing roads, traffic signs)",
                    "Accidents and emergencies",
                    "Basic first aid for cuts, burns, falls",
                    "Emergency numbers and getting help",
                    "Fire safety and prevention",
                ]
            },
            {
                "name": "Environmental Health",
                "order": 5,
                "subtopics": [
                    "Clean environment (home, school, community)",
                    "Proper waste disposal",
                    "Clean water and sanitation",
                    "Mosquito control and malaria prevention",
                    "Planting trees and environmental conservation",
                    "Effects of pollution on health",
                ]
            },
            {
                "name": "Growth and Development",
                "order": 6,
                "subtopics": [
                    "Stages of human growth (infant, child, adolescent, adult)",
                    "Body changes during puberty",
                    "Understanding feelings and emotions",
                    "Respecting personal boundaries",
                    "Reproductive health basics",
                ]
            },
        ]
    },
    "Reading": {
        "code": "P12",
        "topics": [
            {
                "name": "Phonics and Word Recognition",
                "order": 1,
                "subtopics": [
                    "Alphabet recognition (letters A-Z, a-z)",
                    "Letter sounds (phonics)",
                    "Blending sounds to form words",
                    "Sight words and high-frequency words",
                    "Syllables and word parts",
                    "Reading simple words and sentences",
                ]
            },
            {
                "name": "Vocabulary Development",
                "order": 2,
                "subtopics": [
                    "Everyday vocabulary (home, school, community)",
                    "Synonyms and antonyms",
                    "Homophones and homonyms",
                    "Compound words",
                    "Prefixes and suffixes",
                    "Context clues for meaning",
                ]
            },
            {
                "name": "Reading Comprehension",
                "order": 3,
                "subtopics": [
                    "Reading short stories and passages",
                    "Identifying main ideas",
                    "Identifying supporting details",
                    "Sequencing events in a story",
                    "Making predictions and inferences",
                    "Drawing conclusions",
                ]
            },
            {
                "name": "Reading Fluency",
                "order": 4,
                "subtopics": [
                    "Reading with proper pronunciation",
                    "Reading with appropriate speed",
                    "Reading with expression and intonation",
                    "Punctuation awareness when reading",
                    "Repeated reading for fluency",
                    "Reading aloud and silent reading",
                ]
            },
            {
                "name": "Reading Different Texts",
                "order": 5,
                "subtopics": [
                    "Reading stories and folktales",
                    "Reading poems and rhymes",
                    "Reading informational texts",
                    "Reading instructions and directions",
                    "Reading signs, labels and notices",
                    "Reading simple newspapers and magazines",
                ]
            },
            {
                "name": "Critical Reading",
                "order": 6,
                "subtopics": [
                    "Distinguishing fact from opinion",
                    "Identifying author's purpose",
                    "Comparing and contrasting texts",
                    "Making judgments about characters",
                    "Relating texts to personal experience",
                    "Asking questions about texts",
                ]
            },
        ]
    },
    "Writing": {
        "code": "P13",
        "topics": [
            {
                "name": "Handwriting and Letter Formation",
                "order": 1,
                "subtopics": [
                    "Correct pencil grip and posture",
                    "Writing capital letters (A-Z)",
                    "Writing small letters (a-z)",
                    "Writing numbers (0-9)",
                    "Joining letters (cursive writing introduction)",
                    "Writing neatly and legibly",
                ]
            },
            {
                "name": "Spelling and Word Building",
                "order": 2,
                "subtopics": [
                    "Spelling common words correctly",
                    "Spelling rules (i before e, doubling consonants)",
                    "Word families and patterns",
                    "Building longer words from root words",
                    "Using a dictionary for spelling",
                    "Common spelling errors and corrections",
                ]
            },
            {
                "name": "Sentence Structure",
                "order": 3,
                "subtopics": [
                    "Writing complete sentences",
                    "Capitalization rules (start of sentence, proper nouns)",
                    "End punctuation (full stop, question mark, exclamation)",
                    "Subject-verb agreement",
                    "Simple, compound and complex sentences",
                    "Expanding sentences with details",
                ]
            },
            {
                "name": "Paragraph Writing",
                "order": 4,
                "subtopics": [
                    "Parts of a paragraph (topic sentence, details, conclusion)",
                    "Writing descriptive paragraphs",
                    "Writing narrative paragraphs",
                    "Writing informative paragraphs",
                    "Using transition words (first, next, then, finally)",
                    "Organizing paragraphs logically",
                ]
            },
            {
                "name": "Grammar and Mechanics",
                "order": 5,
                "subtopics": [
                    "Nouns (common, proper, plural, possessive)",
                    "Pronouns (personal, possessive, reflexive)",
                    "Verbs (action, linking, helping, tenses)",
                    "Adjectives and adverbs",
                    "Prepositions and conjunctions",
                    "Commas, apostrophes, quotation marks",
                ]
            },
            {
                "name": "Creative and Formal Writing",
                "order": 6,
                "subtopics": [
                    "Writing stories and narratives",
                    "Writing poems and rhymes",
                    "Writing friendly letters",
                    "Writing simple reports",
                    "Writing instructions and procedures",
                    "Writing book reviews",
                ]
            },
        ]
    },
    "Listening": {
        "code": "P14",
        "topics": [
            {
                "name": "Listening for Information",
                "order": 1,
                "subtopics": [
                    "Listening to instructions and following them",
                    "Listening to announcements",
                    "Listening to news and weather reports",
                    "Identifying key information from spoken texts",
                    "Listening to directions",
                    "Listening for specific details",
                ]
            },
            {
                "name": "Listening Comprehension",
                "order": 2,
                "subtopics": [
                    "Listening to stories and answering questions",
                    "Listening to poems and rhymes",
                    "Understanding main ideas from spoken texts",
                    "Sequencing events heard",
                    "Making predictions based on listening",
                    "Drawing conclusions from listening",
                ]
            },
            {
                "name": "Phonological Awareness",
                "order": 3,
                "subtopics": [
                    "Identifying beginning, middle and ending sounds",
                    "Rhyming words",
                    "Syllable segmentation and blending",
                    "Distinguishing similar sounds",
                    "Stress and intonation patterns",
                    "Understanding homophones in context",
                ]
            },
            {
                "name": "Active Listening Skills",
                "order": 4,
                "subtopics": [
                    "Maintaining eye contact and paying attention",
                    "Not interrupting when others speak",
                    "Asking relevant questions",
                    "Paraphrasing and summarizing what was heard",
                    "Showing understanding through body language",
                    "Taking notes while listening",
                ]
            },
            {
                "name": "Listening to Different Audiences",
                "order": 5,
                "subtopics": [
                    "Listening to teachers and classmates",
                    "Listening to guest speakers and visitors",
                    "Listening to audio recordings and broadcasts",
                    "Listening in group discussions",
                    "Listening during assemblies and events",
                    "Listening to telephone conversations",
                ]
            },
        ]
    },
}


KISWAHILI_PRIMARY_SYLLABUS = {
    "Kusoma": {
        "code": "P01",  # Already exists in DB
        "topics": [
            {
                "name": "Kusoma kwa Matamshi",
                "order": 1,
                "subtopics": [
                    "Kutambua herufi za alfabeti (A-Z, a-z)",
                    "Kusoma silabi",
                    "Kusoma maneno kwa matamshi sahihi",
                    "Kusoma vifungu vya maneno",
                    "Kusoma kwa sauti na kwa ukimya",
                    "Kusoma kwa mwendo unaofaa",
                ]
            },
            {
                "name": "Kusoma kwa Ufahamu",
                "order": 2,
                "subtopics": [
                    "Kusoma hadithi fupi na kujibu maswali",
                    "Kutambua wazo kuu katika kifungu",
                    "Kuelewa mfuatano wa matukio",
                    "Kubainisha wahusika na sifa zao",
                    "Kufanya utabiri kuhusu hadithi",
                    "Kuchora hitimisho kutoka kwa kusoma",
                ]
            },
            {
                "name": "Msamiati na Maana ya Maneno",
                "order": 3,
                "subtopics": [
                    "Kujenga msamiati wa kila siku",
                    "Visawe na kinyume maana",
                    "Maana ya maneno katika muktadha",
                    "Misamiati ya nyumbani, shuleni na mtaani",
                    "Nahau na vitendawili",
                    "Methali na misemo",
                ]
            },
            {
                "name": "Kusoma Aina Mbalimbali za Maandishi",
                "order": 4,
                "subtopics": [
                    "Kusoma hadithi na ngano",
                    "Kusoma mashairi na tungo",
                    "Kusoma taarifa na ripoti rahisi",
                    "Kusoma maelekezo na kanuni",
                    "Kusoma matangazo na mabango",
                    "Kusoma magazeti na majarida",
                ]
            },
        ]
    },
    "Kuandika": {
        "code": "P02",  # Already exists in DB
        "topics": [
            {
                "name": "Uandishi wa Herufi na Alama",
                "order": 1,
                "subtopics": [
                    "Kushika penseli kwa usahihi",
                    "Kuandika herufi kubwa (A-Z)",
                    "Kuandika herufi ndogo (a-z)",
                    "Kuandika namba (0-9)",
                    "Kuandika herufi kwa mwandiko mzuri",
                    "Kuandika kwa mtiririko (cursive)",
                ]
            },
            {
                "name": "Uandishi wa Maneno",
                "order": 2,
                "subtopics": [
                    "Kuandika maneno kwa tahajia sahihi",
                    "Kuunda maneno kutoka kwa silabi",
                    "Kuandika maneno ya kila siku",
                    "Kuongeza herufi mwanzo na mwisho wa maneno",
                    "Kurekebisha makosa ya tahajia",
                    "Kutumia kamusi kuangalia tahajia",
                ]
            },
            {
                "name": "Uandishi wa Sentensi",
                "order": 3,
                "subtopics": [
                    "Kuandika sentensi kamili",
                    "Matumizi ya herufi kubwa mwanzoni mwa sentensi",
                    "Matumizi ya alama za uakifishaji (nukta, alama ya swali, mshangao)",
                    "Ulinganifu wa nomino na vitenzi",
                    "Sentensi sahili na sentensi changamano",
                    "Kupanua sentensi kwa maelezo",
                ]
            },
            {
                "name": "Uandishi wa Insha",
                "order": 4,
                "subtopics": [
                    "Sehemu za insha (utangulizi, kiini, hitimisho)",
                    "Kuandika insha za maelezo",
                    "Kuandika insha za simulizi",
                    "Kuandika insha za kubuni",
                    "Kuandika insha za hoja",
                    "Kupanga mawazo kabla ya kuandika",
                ]
            },
            {
                "name": "Uandishi wa Barua na Fomu",
                "order": 5,
                "subtopics": [
                    "Kuandika barua za kirafiki",
                    "Kuandika barua rasmi",
                    "Sehemu za barua (anwani, maelezo, saini)",
                    "Kujaza fomu rahisi",
                    "Kuandika kadi za mwaliko",
                    "Kuandika ujumbe mfupi (notes, text messages)",
                ]
            },
            {
                "name": "Sarufi na Matumizi ya Lugha",
                "order": 6,
                "subtopics": [
                    "Nomino na aina zake",
                    "Vitenzi na nyakati (wakati uliopo, uliopita, ujao)",
                    "Vivumishi na vielezi",
                    "Viwakilishi na viunganishi",
                    "Ngeli za nomino",
                    "Uundaji wa maneno (unyambuaji na utohoaji)",
                ]
            },
        ]
    },
}


PRIMARY_CLASSES = ["Standard 1", "Standard 2", "Standard 3", "Standard 4", "Standard 5", "Standard 6", "Standard 7"]


class Command(BaseCommand):
    help = "Seed English Medium Primary School subjects with topics and subtopics"

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, help='Subject name to seed (case-insensitive)')
        parser.add_argument('--list', action='store_true', help='List subjects that will be seeded')

    def handle(self, *args, **options):
        if options['list']:
            self.list_subjects()
            return

        subject_filter = options.get('subject')
        all_data = {**PRIMARY_SYLLABUS, **KISWAHILI_PRIMARY_SYLLABUS}

        if subject_filter:
            matched = {}
            for name, data in all_data.items():
                if subject_filter.lower() in name.lower():
                    matched[name] = data
            if not matched:
                self.stdout.write(self.style.ERROR(
                    f"Subject '{subject_filter}' not found. Available: {', '.join(all_data.keys())}"
                ))
                return
            all_data = matched

        total_subjects = 0
        total_topics = 0
        total_subtopics = 0

        for subject_name, subject_data in all_data.items():
            with transaction.atomic():
                # Try to get existing subject by name or code
                subj = Subject.objects.filter(name=subject_name).first()
                if not subj:
                    subj = Subject.objects.filter(code=subject_data['code']).first()

                created = False
                if not subj:
                    subj = Subject.objects.create(
                        name=subject_name,
                        code=subject_data['code'],
                        level='primary',
                    )
                    created = True
                    self.stdout.write(f"  ✅ Created: {subject_name} (code={subj.code})")
                else:
                    # Update level to primary if needed
                    if subj.level != 'primary':
                        subj.level = 'primary'
                        subj.save()
                    self.stdout.write(f"  🔄 Already exists: {subject_name} (code={subj.code}, level={subj.level})")

                # Create topics for each primary class
                for topic_data in subject_data['topics']:
                    for class_name in PRIMARY_CLASSES:
                        topic, t_created = SubjectTopic.objects.get_or_create(
                            subject=subj,
                            class_name=class_name,
                            name=topic_data['name'],
                            defaults={'order': topic_data['order']}
                        )

                        if t_created:
                            for sub_order, subtopic_name in enumerate(topic_data['subtopics'], 1):
                                TopicSubtopic.objects.get_or_create(
                                    topic=topic,
                                    name=subtopic_name,
                                    defaults={'order': sub_order}
                                )
                            total_subtopics += len(topic_data['subtopics'])
                            total_topics += 1
                        else:
                            # Also ensure subtopics exist for existing topics
                            existing_sub_names = set(
                                TopicSubtopic.objects.filter(topic=topic)
                                .values_list('name', flat=True)
                            )
                            for sub_order, subtopic_name in enumerate(topic_data['subtopics'], 1):
                                if subtopic_name not in existing_sub_names:
                                    TopicSubtopic.objects.get_or_create(
                                        topic=topic,
                                        name=subtopic_name,
                                        defaults={'order': sub_order}
                                    )

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Done! Processed {len(all_data)} subject(s) with {total_topics} new topics and {total_subtopics} subtopics"
        ))

    def list_subjects(self):
        all_data = {**PRIMARY_SYLLABUS, **KISWAHILI_PRIMARY_SYLLABUS}
        self.stdout.write("\n📚 English Medium Primary School Subjects:")
        self.stdout.write("=" * 60)
        for name, data in all_data.items():
            topics_count = len(data['topics'])
            subtopics_count = sum(len(t.get('subtopics', [])) for t in data['topics'])
            status = "⚠️ exists" if Subject.objects.filter(name=name).exists() else "➕ new"
            self.stdout.write(f"  • {name} (code={data['code']}): {topics_count} topics, {subtopics_count} subtopics [{status}]")
        self.stdout.write(f"\nTotal: {len(all_data)} subjects")
        self.stdout.write(f"Classes: {', '.join(PRIMARY_CLASSES)}")
