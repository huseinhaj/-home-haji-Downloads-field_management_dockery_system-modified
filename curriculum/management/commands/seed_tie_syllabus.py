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
from curriculum.management.data.additional_subjects_data import get_additional_form_data

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
                    "Basic concepts and terminologies in Biology",
                    "Branches of Biology",
                    "Characteristics of living things",
                    "Importance of studying Biology",
                    "Relationship between Biology and other scientific fields",
                ]
            },
            {
                "name": "Scientific processes in Biology",
                "order": 2,
                "subtopics": [
                    "Common Biology laboratory apparati, equipment and other resources",
                    "Basic skills in scientific studies",
                    "Scientific methods",
                    "Simple biological experiments",
                ]
            },
            {
                "name": "Cell structure and organization",
                "order": 3,
                "subtopics": [
                    "The cell",
                    "Types of cells",
                    "Animal and plant cells",
                    "Cell differentiation",
                ]
            },
            {
                "name": "Classification of living things",
                "order": 4,
                "subtopics": [
                    "Concept of classification",
                    "Classification systems",
                    "Major groups of living things",
                    "Binomial nomenclature",
                ]
            },
            {
                "name": "Viruses and major groups of living things",
                "order": 5,
                "subtopics": [
                    "Viruses",
                    "Kingdom Monera",
                    "Kingdom Protoctista",
                    "Kingdom Fungi",
                    "Kingdom Plantae",
                    "Classes of the division Angiospermophyta",
                    "Kingdom Animalia",
                ]
            },
            {
                "name": "Nutrition in plants",
                "order": 6,
                "subtopics": [
                    "Concept of nutrition",
                    "Photosynthesis",
                    "Structure of the leaf in relation to photosynthesis",
                    "Importance of photosynthesis",
                    "Essential and non-essential elements in plants",
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


# =============================================================================
# FORM 2 TOPICS & SUBTOPICS — TIE Official Syllabus
# =============================================================================

FORM_2_SYLLABUS = {
    "Mathematics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Rates and Variations", "order": 1, "subtopics": ["Direct variation", "Inverse variation", "Joint variation", "Applications of variation"]},
            {"name": "Congruence", "order": 2, "subtopics": ["Concept of congruence", "Congruence postulates", "Applications of congruence"]},
            {"name": "Similarity", "order": 3, "subtopics": ["Concept of similarity", "Similarity of triangles", "Applications of similarity"]},
            {"name": "Algebra", "order": 4, "subtopics": ["Factorization", "Quadratic expressions", "Quadratic equations", "Simultaneous equations"]},
            {"name": "Exponents and Radicals", "order": 5, "subtopics": ["Laws of exponents", "Zero and negative exponents", "Radicals and surds", "Rationalization"]},
            {"name": "Logarithms", "order": 6, "subtopics": ["Concept of logarithms", "Laws of logarithms", "Applications of logarithms", "Using mathematical tables"]},
            {"name": "Sets", "order": 7, "subtopics": ["Concept of sets", "Set operations", "Venn diagrams", "Applications of sets"]},
            {"name": "Trigonometry", "order": 8, "subtopics": ["Trigonometric ratios", "Sine and cosine of complementary angles", "Solving right-angled triangles", "Applications of trigonometry"]},
        ]
    },
    "English": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Talking About Food and Health", "order": 1, "subtopics": ["Vocabulary related to food and health", "Expressing quantity", "Giving advice on health"]},
            {"name": "Talking About Work and Careers", "order": 2, "subtopics": ["Vocabulary for jobs and professions", "Expressing future intentions", "Modal verbs for obligation"]},
            {"name": "Describing Places and Things", "order": 3, "subtopics": ["Adjectives for description", "Comparative and superlative adjectives", "Relative clauses"]},
            {"name": "Expressing Preferences", "order": 4, "subtopics": ["Expressing likes and dislikes", "Making comparisons", "Giving reasons"]},
            {"name": "Narrating Events", "order": 5, "subtopics": ["Past continuous tense", "Sequence of events", "Connecting words for narration"]},
            {"name": "Reading for Comprehension", "order": 6, "subtopics": ["Reading different text types", "Identifying main ideas", "Making inferences"]},
            {"name": "Writing Formal Letters", "order": 7, "subtopics": ["Format of formal letters", "Language for formal correspondence", "Job application letters"]},
            {"name": "Listening for Information", "order": 8, "subtopics": ["Listening to announcements", "Listening for specific details", "Following instructions"]},
        ]
    },
    "Kiswahili": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Uundaji wa Maneno", "order": 1, "subtopics": ["Unyambuaji wa maneno", "Utoaji wa maneno", "Mofimu na mofu"]},
            {"name": "Ngeli za Nomino", "order": 2, "subtopics": ["Dhana ya ngeli", "Ngeli za Kiswahili", "Matumizi ya ngeli"]},
            {"name": "Matumizi ya Lugha Katika Mazingira", "order": 3, "subtopics": ["Lugha ya mitaani", "Athari za lugha za kigeni", "Usanifu wa lugha"]},
            {"name": "Fasihi Andishi", "order": 4, "subtopics": ["Dhana ya fasihi andishi", "Tanzu za fasihi andishi", "Uchambuzi wa kazi za fasihi andishi"]},
            {"name": "Uandishi wa Insha za Kisanaa", "order": 5, "subtopics": ["Insha za kubuni", "Insha za maelezo", "Insha za hoja"]},
        ]
    },
    "Biology": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Nutrition in animals", "order": 1, "subtopics": [
                "Concept of nutrition in animals",
                "Nutrients",
                "Balanced diet",
                "Nutritional requirements for different groups of people",
                "Nutritional deficiencies and disorders",
                "Properties of food nutrients",
            ]},
            {"name": "Digestive system", "order": 2, "subtopics": [
                "The digestion process",
                "The digestive system of ruminants",
                "Disorders and diseases of human digestive system",
            ]},
            {"name": "Transport of materials in living organisms", "order": 3, "subtopics": [
                "Concept of transportation of materials",
                "Ways of transportation of materials",
            ]},
            {"name": "Transport of materials in flowering plants", "order": 4, "subtopics": [
                "The vascular system",
                "Absorption and movement of water and mineral salts",
                "Transpiration",
                "Guttation",
            ]},
            {"name": "Transport of materials in mammals", "order": 5, "subtopics": [
                "The mammalian heart",
                "Blood vessels",
                "The blood",
                "Blood groups",
                "Blood transfusion",
                "Blood circulation in human beings",
            ]},
            {"name": "Gas exchange and respiration", "order": 6, "subtopics": [
                "Concept of gas exchange",
                "Gas exchange in mammals",
                "Gas exchange in plants",
                "Respiration in mammals",
                "Infections and diseases of the respiratory system in humans",
            ]},
        ]
    },
    "Physics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Static Electricity", "order": 1, "subtopics": ["Concept of static electricity", "Charging methods", "Electroscope", "Applications of static electricity"]},
            {"name": "Current Electricity", "order": 2, "subtopics": ["Electric current", "Potential difference", "Resistance and Ohm's law", "Electrical circuits"]},
            {"name": "Heat Transfer", "order": 3, "subtopics": ["Heat conduction", "Convection", "Radiation", "Applications of heat transfer"]},
            {"name": "Magnetism", "order": 4, "subtopics": ["Concept of magnetism", "Types of magnets", "Magnetic field", "Applications of magnetism"]},
            {"name": "Motion", "order": 5, "subtopics": ["Concept of motion", "Speed, velocity and acceleration", "Equations of motion", "Graphs of motion"]},
            {"name": "Newton's Laws of Motion", "order": 6, "subtopics": ["First law of motion", "Second law of motion", "Third law of motion", "Applications"]},
            {"name": "Simple Machines", "order": 7, "subtopics": ["Concept of simple machines", "Levers", "Pulleys", "Inclined plane and screw", "Mechanical advantage"]},
        ]
    },
    "Chemistry": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Bonding and Nomenclature", "order": 1, "subtopics": ["Chemical bonding", "Ionic and covalent bonding", "Naming chemical compounds", "Writing chemical formulae"]},
            {"name": "Periodic Classification of Elements", "order": 2, "subtopics": ["The periodic table", "Groups and periods", "Chemical families", "Trends in the periodic table"]},
            {"name": "Chemical Equations and Reactions", "order": 3, "subtopics": ["Writing chemical equations", "Balancing equations", "Types of chemical reactions", "Factors affecting reactions"]},
            {"name": "Acids, Bases and Salts", "order": 4, "subtopics": ["Concept of acids and bases", "pH scale", "Indicators", "Salts and preparation methods"]},
            {"name": "The Mole Concept", "order": 5, "subtopics": ["The mole", "Molar mass", "Molar volume", "Avogadro's number"]},
            {"name": "Electrochemistry", "order": 6, "subtopics": ["Conductivity of solutions", "Electrolysis", "Electrolytic cells", "Applications of electrolysis"]},
        ]
    },
    "History": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Interactions Among the Pre-colonial People of Africa", "order": 1, "subtopics": ["Migration theories", "The Ngoni migration", "Forces of interaction", "Effects of interactions"]},
            {"name": "Socio-economic Development in Pre-colonial Africa", "order": 2, "subtopics": ["Agricultural development", "Artisanal activities", "Organization of production"]},
            {"name": "Early Contacts Between Africa, Middle East and Far East", "order": 3, "subtopics": ["Indian Ocean trade", "Swahili civilization", "Dhow trade", "Impact of early contacts"]},
            {"name": "Early Contacts Between Africa and Europe", "order": 4, "subtopics": ["Portuguese exploration", "Portuguese rule on East African coast", "Impact of Portuguese presence"]},
            {"name": "Africa and the Slave Trade", "order": 5, "subtopics": ["Trans-Saharan slave trade", "Indian Ocean slave trade", "Trans-Atlantic slave trade", "Transition to legitimate trade"]},
            {"name": "Industrial Capitalism", "order": 6, "subtopics": ["Rise of industrialization", "Need for raw materials", "Impact on Africa", "Scramble for Africa"]},
        ]
    },
    "Geography": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Internal Structure of the Earth", "order": 1, "subtopics": ["Layers of the Earth", "Crust, mantle and core", "Internal forces shaping Earth"]},
            {"name": "Landform Processes", "order": 2, "subtopics": ["Weathering", "Erosion", "Mass wasting", "Deposition"]},
            {"name": "Map Reading and Interpretation", "order": 3, "subtopics": ["Topographical maps", "Grid references", "Scale and distance", "Conventional signs"]},
            {"name": "Photograph Reading and Interpretation", "order": 4, "subtopics": ["Ground photographs", "Aerial photographs", "Photo interpretation skills"]},
            {"name": "Climate and Weather", "order": 5, "subtopics": ["Climatic regions", "Weather elements", "Factors influencing climate", "Climate change"]},
            {"name": "Human Activities", "order": 6, "subtopics": ["Agriculture systems", "Mining and minerals", "Fishing and forestry", "Tourism", "Manufacturing industry", "Transport and settlement"]},
        ]
    },
    "Civics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Promotion of Life Skills", "order": 1, "subtopics": ["Identifying social problems", "Problem-solving techniques", "Importance of life skills"]},
            {"name": "The Government of the United Republic of Tanzania", "order": 2, "subtopics": ["Concept and types of government", "State authorities", "Local government structure", "Union matters"]},
            {"name": "The Constitution of the United Republic of Tanzania", "order": 3, "subtopics": ["Concept and types of constitutions", "Structure of the 1977 Constitution", "Constitutional principles", "History of Tanzanian constitution"]},
            {"name": "Democracy", "order": 4, "subtopics": ["Concept and principles of democracy", "Types of democracy", "Multiparty democracy", "Democratic elections"]},
            {"name": "Gender", "order": 5, "subtopics": ["Gender concepts", "Gender issues in society", "Women's empowerment", "Gender equality"]},
        ]
    },
}


# =============================================================================
# FORM 3 TOPICS & SUBTOPICS — TIE Official Syllabus
# =============================================================================

FORM_3_SYLLABUS = {
    "Mathematics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Relations", "order": 1, "subtopics": ["Concept of relations", "Types of relations", "Representation of relations", "Domain and range"]},
            {"name": "Functions", "order": 2, "subtopics": ["Concept of a function", "Linear functions", "Quadratic functions", "Graphs of functions", "Inverse of a function"]},
            {"name": "Statistics", "order": 3, "subtopics": ["Concept of statistics", "Data collection and presentation", "Measures of central tendency", "Measures of dispersion", "Interpretation of data"]},
            {"name": "Probability", "order": 4, "subtopics": ["Concept of probability", "Probability rules", "Tree diagrams", "Applications of probability"]},
            {"name": "Sequences and Series", "order": 5, "subtopics": ["Arithmetic sequences", "Arithmetic series", "Geometric sequences", "Geometric series", "Applications"]},
            {"name": "Circles", "order": 6, "subtopics": ["Equation of a circle", "Properties of circles", "Tangents to circles"]},
            {"name": "Earth as a Sphere", "order": 7, "subtopics": ["Concept of longitude and latitude", "Great circles", "Small circles", "Distance along great circles", "Distance along small circles", "Time"]},
        ]
    },
    "English": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Talking About Education", "order": 1, "subtopics": ["Vocabulary for education", "Discussing school life", "Talking about study habits", "Giving opinions on education"]},
            {"name": "Discussing Health and Social Issues", "order": 2, "subtopics": ["Health vocabulary", "Discussing social problems", "Giving advice and suggestions", "Expressing cause and effect"]},
            {"name": "Expressing Opinions and Feelings", "order": 3, "subtopics": ["Expressing agreement and disagreement", "Making judgments", "Arguing persuasively"]},
            {"name": "Reading for Detailed Comprehension", "order": 4, "subtopics": ["Identifying author's purpose", "Evaluating information", "Critical reading", "Summarizing"]},
            {"name": "Writing Reports and Articles", "order": 5, "subtopics": ["Structure of reports", "Language for reports", "Writing newspaper articles", "Writing magazine articles"]},
            {"name": "Listening and Speaking to Different Audiences", "order": 6, "subtopics": ["Public speaking skills", "Formal presentations", "Adjusting language for audience", "Debate preparation"]},
            {"name": "Compound and Complex Sentences", "order": 7, "subtopics": ["Compound sentences", "Complex sentences", "Using connectives", "Sentence transformation"]},
        ]
    },
    "Kiswahili": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Uhakiki wa Fasihi", "order": 1, "subtopics": ["Dhana ya uhakiki", "Vigezo vya uhakiki", "Uhakiki wa hadithi fupi", "Uhakiki wa riwaya", "Uhakiki wa tamthilia"]},
            {"name": "Ushairi", "order": 2, "subtopics": ["Dhana ya ushairi", "Aina za mashairi", "Vipengele vya ushairi", "Uchambuzi wa mashairi", "Uhakiki wa mashairi"]},
            {"name": "Insha za Hoja na Makala", "order": 3, "subtopics": ["Insha za hoja", "Makala", "Uandishi wa makala", "Mbinu za kusadikisha"]},
            {"name": "Utamaduni na Mila", "order": 4, "subtopics": ["Dhana ya utamaduni", "Vipengele vya utamaduni", "Athari za mabadiliko ya utamaduni", "Kuhifadhi utamaduni"]},
            {"name": "Matumizi ya Lugha", "order": 5, "subtopics": ["Misamiati", "Nahau na vitendawili", "Istilahi", "Pragmatism katika lugha"]},
        ]
    },
    "Biology": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Reproduction", "order": 1, "subtopics": ["Concept of reproduction", "Types of reproduction", "Cell division (mitosis and meiosis)", "Significance of cell division"]},
            {"name": "Reproduction in Plants", "order": 2, "subtopics": ["Asexual reproduction in plants", "Sexual reproduction in plants", "Pollination", "Fertilization and seed formation", "Fruit and seed dispersal"]},
            {"name": "Reproduction in Mammals", "order": 3, "subtopics": ["Male reproductive system", "Female reproductive system", "Menstrual cycle", "Fertilization and implantation", "Pregnancy and development", "Birth control methods"]},
            {"name": "Growth", "order": 4, "subtopics": ["Concept of growth", "Measurement of growth", "Growth curves", "Factors affecting growth", "Growth in plants and animals"]},
            {"name": "Regulation (Homeostasis)", "order": 5, "subtopics": ["Concept of homeostasis", "Temperature regulation", "Osmoregulation", "Blood sugar regulation", "Feedback mechanisms"]},
            {"name": "Genetics", "order": 6, "subtopics": ["Concept of genetics", "Mendelian inheritance", "Monohybrid cross", "Dihybrid cross", "Sex determination", "Sex-linked inheritance", "Genetic disorders"]},
            {"name": "Evolution", "order": 7, "subtopics": ["Concept of evolution", "Evidence of evolution", "Theories of evolution (Lamarck, Darwin)", "Natural selection", "Mechanisms of speciation"]},
        ]
    },
    "Physics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Vectors and Scalars", "order": 1, "subtopics": ["Concept of vectors", "Vector representation", "Addition of vectors", "Resolution of vectors", "Applications"]},
            {"name": "Projectile Motion", "order": 2, "subtopics": ["Concept of projectile", "Horizontal projection", "Angled projection", "Range, time of flight, maximum height", "Applications"]},
            {"name": "Friction", "order": 3, "subtopics": ["Concept of friction", "Types of friction", "Coefficient of friction", "Advantages and disadvantages of friction", "Applications"]},
            {"name": "Light (Lenses and Optical Instruments)", "order": 4, "subtopics": ["Types of lenses", "Image formation by lenses", "Lens formula", "Optical instruments (microscope, telescope, camera)"]},
            {"name": "Waves", "order": 5, "subtopics": ["Concept of waves", "Types of waves", "Properties of waves", "Applications of waves"]},
            {"name": "Sound", "order": 6, "subtopics": ["Concept of sound", "Propagation of sound", "Characteristics of sound", "Echo and reverberation", "Applications of sound"]},
            {"name": "Electrostatics II", "order": 7, "subtopics": ["Electric field", "Electric field intensity", "Electric potential", "Capacitance and capacitors", "Applications"]},
            {"name": "Current Electricity II", "order": 8, "subtopics": ["Electromotive force", "Internal resistance", "Electrical energy and power", "Series and parallel circuits"]},
        ]
    },
    "Chemistry": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Chemical Equations and Reactions", "order": 1, "subtopics": ["Balancing equations", "Types of chemical reactions", "Oxidation and reduction (Redox reactions)", "Ionic equations"]},
            {"name": "Acids, Bases and Salts II", "order": 2, "subtopics": ["Properties of acids and bases", "Strength of acids and bases", "pH calculations", "Hydrolysis of salts", "Buffer solutions"]},
            {"name": "Mole Concept II (Stoichiometry)", "order": 3, "subtopics": ["Empirical and molecular formulae", "Percentage composition", "Stoichiometric calculations", "Limiting reagents", "Percentage yield"]},
            {"name": "Volumetric Analysis", "order": 4, "subtopics": ["Concept of titration", "Standard solutions", "Acid-base titrations", "Concentration calculations"]},
            {"name": "Organic Chemistry I (Introduction)", "order": 5, "subtopics": ["Carbon compounds", "Homologous series", "Functional groups", "Hydrocarbons: alkanes, alkenes, alkynes", "Naming organic compounds"]},
            {"name": "Organic Chemistry II (Derivatives)", "order": 6, "subtopics": ["Alcohols", "Carboxylic acids", "Esters", "Polymers", "Natural and synthetic polymers"]},
        ]
    },
    "History": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Establishment of Colonial Rule in Africa", "order": 1, "subtopics": ["The Berlin Conference", "Methods of establishing colonial rule", "Colonial administration systems (direct and indirect rule)", "African reactions to colonial rule"]},
            {"name": "Colonial Administrative Systems in Africa", "order": 2, "subtopics": ["Assimilation policy (French)", "Indirect rule (British)", "Direct rule (German, Portuguese)", "Impact of colonial administration"]},
            {"name": "Social and Economic Changes in Colonial Africa", "order": 3, "subtopics": ["Cash crop economy", "Mining and extraction", "Colonial taxation", "Migration and labour", "Urbanization", "Social services and education"]},
            {"name": "Rise of African Nationalism", "order": 4, "subtopics": ["Factors for rise of nationalism", "Forms of nationalism", "Nationalist movements", "Role of trade unions and associations", "Role of WWII in decolonization"]},
            {"name": "Decolonization Process in Africa", "order": 5, "subtopics": ["Constitutional changes", "Independence movements (Ghana, Kenya, Tanganyika)", "Methods of achieving independence", "Pan-Africanism", "Role of the UN"]},
        ]
    },
    "Geography": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Statistical Methods", "order": 1, "subtopics": ["Data collection methods", "Data presentation (graphs, charts, diagrams)", "Data interpretation", "Measures of central tendency", "Measures of dispersion"]},
            {"name": "Soil", "order": 2, "subtopics": ["Concept of soil", "Soil formation processes", "Soil profile and horizons", "Soil types and properties", "Soil conservation methods"]},
            {"name": "Agriculture", "order": 3, "subtopics": ["Types of agriculture", "Subsistence and commercial farming", "Agricultural systems in Tanzania", "Factors affecting agriculture", "Agricultural problems and solutions"]},
            {"name": "Water Management and Irrigation", "order": 4, "subtopics": ["Water sources and uses", "Water management techniques", "Irrigation methods", "Water conservation"]},
            {"name": "Surveying", "order": 5, "subtopics": ["Concept of surveying", "Types of surveying (plane, geodetic, aerial)", "Surveying equipment", "Chain surveying", "Compass surveying", "Uses of surveying"]},
            {"name": "Environmental Management", "order": 6, "subtopics": ["Environmental problems", "Deforestation", "Pollution", "Climate change", "Conservation strategies"]},
        ]
    },
    "Civics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Government Systems in the World", "order": 1, "subtopics": ["Unitary government", "Federal government", "Presidential system", "Parliamentary system", "Comparative analysis"]},
            {"name": "Political Parties and Electoral Systems", "order": 2, "subtopics": ["Concept of political parties", "Functions of political parties", "Types of party systems", "Electoral systems", "Free and fair elections"]},
            {"name": "The Constitution II", "order": 3, "subtopics": ["Constitutional amendments", "Constitutional enforcement", "Separation of powers", "Checks and balances", "Rule of law"]},
            {"name": "Conflict Resolution", "order": 4, "subtopics": ["Types of conflicts", "Causes of conflicts", "Conflict resolution methods", "Peace building", "International peace organizations (UN, AU)"]},
            {"name": "International Relations and Cooperation", "order": 5, "subtopics": ["Diplomacy", "International organizations (UN, AU, EAC, SADC)", "Treaties and agreements", "Tanzania's foreign policy", "Globalization"]},
        ]
    },
}


# =============================================================================
# FORM 4 TOPICS & SUBTOPICS — TIE Official Syllabus
# =============================================================================

FORM_4_SYLLABUS = {
    "Mathematics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Vectors", "order": 1, "subtopics": ["Concept of vectors", "Vector operations", "Position vectors", "Unit vectors", "Applications of vectors"]},
            {"name": "Matrices and Transformations", "order": 2, "subtopics": ["Concept of matrices", "Matrix operations", "Determinants", "Inverse of a matrix", "Transformation matrices", "Applications"]},
            {"name": "Linear Programming", "order": 3, "subtopics": ["Concept of linear programming", "Formulating linear programming problems", "Graphical method", "Simplex method (introduction)", "Applications in decision making"]},
            {"name": "Probability", "order": 4, "subtopics": ["Probability of compound events", "Conditional probability", "Mutually exclusive events", "Independent events", "Bayes' theorem (introduction)"]},
            {"name": "Statistics II", "order": 5, "subtopics": ["Cumulative frequency", "Quartiles and percentiles", "Histograms and frequency polygons", "Correlation", "Regression"]},
            {"name": "Three-Dimensional Geometry", "order": 6, "subtopics": ["Points in 3D space", "Distance formula in 3D", "Equations of lines in 3D", "Equations of planes", "Angles between lines and planes"]},
        ]
    },
    "English": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Expressing and Interpreting Information", "order": 1, "subtopics": ["Interpreting charts and graphs", "Transformational grammar", "Reading for critical evaluation", "Summarizing and note-taking"]},
            {"name": "Negotiating and Persuading", "order": 2, "subtopics": ["Negotiation strategies", "Persuasion techniques", "Compromise and consensus", "Diplomatic language"]},
            {"name": "Public Speaking and Debating", "order": 3, "subtopics": ["Speech writing", "Vocal delivery techniques", "Debate formats", "Rebuttal strategies", "Evaluating speeches"]},
            {"name": "Creative Writing", "order": 4, "subtopics": ["Short story writing", "Poetry writing", "Play writing", "Descriptive and narrative techniques"]},
            {"name": "Research and Academic Writing", "order": 5, "subtopics": ["Writing research proposals", "Data collection instruments", "Report writing", "Referencing and citation", "Academic integrity"]},
            {"name": "Grammar and Language Structure", "order": 6, "subtopics": ["Advanced sentence structures", "Phrasal verbs and idioms", "Word formation", "Style and register"]},
        ]
    },
    "Kiswahili": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Fasihi kwa Ujumla (Mapitio na Uchambuzi)", "order": 1, "subtopics": ["Aina za fasihi na tanzu zake", "Uhakiki wa kazi za fasihi andishi", "Uhakiki wa fasihi simulizi", "Nadharia za uhakiki wa fasihi"]},
            {"name": "Riwaya na Tamthilia", "order": 2, "subtopics": ["Dhana ya riwaya", "Mbinu za riwaya", "Dhana ya tamthilia", "Mbinu za tamthilia", "Uchambuzi wa riwaya na tamthilia"]},
            {"name": "Uandishi Bunifu", "order": 3, "subtopics": ["Uandishi wa insha bunifu", "Uandishi wa hadithi fupi", "Uandishi wa ushairi", "Uandishi wa tamthilia"]},
            {"name": "Lugha na Sarufi", "order": 4, "subtopics": ["Uchambuzi wa sarufi", "Matumizi ya lugha katika miktadha mbalimbali", "Athari za lugha", "Maana na uamilifu wa lugha"]},
            {"name": "Tafiti na Makala", "order": 5, "subtopics": ["Utayarishaji wa pendekezo la utafiti", "Utekelezaji wa utafiti", "Uandishi wa taarifa ya utafiti", "Uwasilishaji wa matokeo"]},
        ]
    },
    "Biology": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Genetics II", "order": 1, "subtopics": ["DNA structure and replication", "Protein synthesis", "Gene expression", "Mutations", "Biotechnology and genetic engineering"]},
            {"name": "Evolution II", "order": 2, "subtopics": ["Mechanisms of evolution", "Adaptive radiation", "Convergent and divergent evolution", "Evidence for evolution from molecular biology"]},
            {"name": "Ecology", "order": 3, "subtopics": ["Concept of ecosystem", "Population ecology", "Community ecology", "Energy flow in ecosystems", "Nutrient cycling", "Ecological succession"]},
            {"name": "Human Health", "order": 4, "subtopics": ["Non-communicable diseases", "Nutrition and health", "Mental health", "Substance abuse", "Community health programs"]},
            {"name": "Biotechnology and Environmental Conservation", "order": 5, "subtopics": ["Principles of biotechnology", "Agricultural biotechnology", "Medical biotechnology", "Conservation of biodiversity", "Environmental impact assessment"]},
        ]
    },
    "Physics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Electromagnetism", "order": 1, "subtopics": ["Magnetic fields from currents", "Electromagnetic induction", "A.C. and D.C. generators", "Motors", "Transformers"]},
            {"name": "Electronics", "order": 2, "subtopics": ["Semiconductors", "Diodes", "Transistors", "Integrated circuits", "Applications of electronics"]},
            {"name": "Radioactivity", "order": 3, "subtopics": ["Atomic structure", "Types of radiation", "Radioactive decay", "Half-life", "Nuclear fission and fusion", "Uses of radioactivity"]},
            {"name": "Astronomy and Space Exploration", "order": 4, "subtopics": ["The universe and galaxies", "Stars and stellar evolution", "Space exploration", "Satellites and their uses"]},
            {"name": "Energy Sources and Management", "order": 5, "subtopics": ["Renewable energy sources", "Non-renewable energy sources", "Energy efficiency", "Environmental impact of energy use"]},
        ]
    },
    "Chemistry": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Chemical Kinetics and Equilibrium", "order": 1, "subtopics": ["Reaction rates", "Factors affecting reaction rates", "Chemical equilibrium", "Le Chatelier's principle", "Applications of equilibrium"]},
            {"name": "Inorganic Chemistry", "order": 2, "subtopics": ["Periodic trends", "Chemistry of Group I and II elements", "Chemistry of Group VII elements", "Transition metals", "Qualitative analysis"]},
            {"name": "Organic Chemistry III", "order": 3, "subtopics": ["Reaction mechanisms", "Addition reactions", "Substitution reactions", "Elimination reactions", "Organic synthesis"]},
            {"name": "Environmental Chemistry", "order": 4, "subtopics": ["Pollution types (air, water, soil)", "Greenhouse effect", "Acid rain", "Ozone depletion", "Waste management", "Green chemistry"]},
            {"name": "Soil Chemistry", "order": 5, "subtopics": ["Soil composition", "Soil pH and nutrients", "Fertilizers", "Soil pollution and remediation"]},
        ]
    },
    "History": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Changes in Political Systems in Independent African Countries", "order": 1, "subtopics": ["One-party states", "Military regimes", "Multi-party systems", "Challenges of democratization", "Civil conflicts and resolution"]},
            {"name": "Economic Development and Challenges in Africa Since Independence", "order": 2, "subtopics": ["Development strategies (African socialism, capitalism)", "Structural adjustment programs", "Debt crisis", "Economic cooperation (EAC, SADC, ECOWAS)", "NEPAD and AGENDA 2063"]},
            {"name": "Social Changes in Africa Since Independence", "order": 3, "subtopics": ["Education development", "Health services", "Urbanization", "Gender and women empowerment", "Youth and social welfare"]},
            {"name": "International Relations in Africa Since Independence", "order": 4, "subtopics": ["Non-alignment movement", "OAU and AU", "Regional integration", "Globalization and Africa", "Africa in the UN system"]},
        ]
    },
    "Geography": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Population", "order": 1, "subtopics": ["Population distribution and density", "Population structure", "Population dynamics (birth, death, migration)", "Population theories", "Population problems and policies"]},
            {"name": "Settlement", "order": 2, "subtopics": ["Types of settlements", "Rural settlement patterns", "Urban settlement patterns", "Urbanization process", "Urban planning and management"]},
            {"name": "Mining and Mineral Resources", "order": 3, "subtopics": ["Types of minerals", "Mining methods", "Mining in Tanzania", "Economic importance of minerals", "Environmental impact of mining"]},
            {"name": "Industry and Industrialization", "order": 4, "subtopics": ["Types of industries", "Factors influencing industrial location", "Industrialization in Tanzania", "Industrialization strategies", "Industrial development challenges"]},
            {"name": "Transport and Communication", "order": 5, "subtopics": ["Modes of transport", "Transport networks and development", "Communication systems", "ICT development", "Role of transport in economic development"]},
            {"name": "Natural Resources and Conservation", "order": 6, "subtopics": ["Types of natural resources", "Resource management", "Sustainable development", "Wildlife conservation", "Forestry conservation"]},
        ]
    },
    "Civics": {
        "subject_code": "secondary",
        "topics": [
            {"name": "Culture and National Identity", "order": 1, "subtopics": ["Concept of culture", "Components of culture", "Cultural diversity in Tanzania", "National cohesion and unity", "Cultural preservation"]},
            {"name": "Economic Development and Planning", "order": 2, "subtopics": ["Economic development concepts", "Development plans in Tanzania", "Budget making process", "Public expenditure and revenue", "Economic sectors"]},
            {"name": "Informal Sector and Entrepreneurship", "order": 3, "subtopics": ["Concept of informal sector", "Entrepreneurship skills", "Business plan development", "Small and medium enterprises", "Youth employment and self-reliance"]},
            {"name": "Globalization and International Cooperation", "order": 4, "subtopics": ["Concept and dimensions of globalization", "Effects of globalization", "International cooperation", "Tanzania in global affairs", "Global governance"]},
            {"name": "Human Rights and Responsibilities", "order": 5, "subtopics": ["International human rights instruments", "Individual and group rights", "Constitutional rights in Tanzania", "Responsibilities of citizens", "Human rights enforcement mechanisms"]},
            {"name": "Voter Education and Democratic Participation", "order": 6, "subtopics": ["Electoral process", "Voter registration", "Voting procedures", "Role of observers", "Post-election governance"]},
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

        # Filter syllabus data by form
        form_map = {
            '1': ('FORM_1_SYLLABUS', 'Form 1'),
            '2': ('FORM_2_SYLLABUS', 'Form 2'),
            '3': ('FORM_3_SYLLABUS', 'Form 3'),
            '4': ('FORM_4_SYLLABUS', 'Form 4'),
        }
        if form and form not in form_map:
            self.stdout.write(self.style.WARNING(
                f"⚠️ Form {form} data not available. Use 1, 2, 3 or 4."
            ))
            return
        
        if form:
            # Seed only the specified form
            if form not in form_map:
                self.stdout.write(self.style.WARNING(f"⚠️ Form {form} data not available. Use 1, 2, 3 or 4."))
                return
            var_name, display_name = form_map[form]
            syllabus_data = globals()[var_name]
            
            # Merge additional subjects data BEFORE filtering
            additional_data = get_additional_form_data(int(form))
            syllabus_data = {**syllabus_data, **additional_data}
            
            if subject_name:
                matched = {}
                for name, data in syllabus_data.items():
                    if subject_name.lower() in name.lower():
                        matched[name] = data
                if not matched:
                    self.stdout.write(self.style.ERROR(
                        f"✗ Subject '{subject_name}' not found in Form {form}. Available: {', '.join(syllabus_data.keys())}"
                    ))
                    return
                syllabus_data = matched
            
            self.seed_data(syllabus_data, form)
        else:
            # No form specified — seed all forms
            for f_num in ['1', '2', '3', '4']:
                var_name, display_name = form_map[f_num]
                all_data = globals()[var_name]
                
                # Merge additional subjects data BEFORE filtering
                additional_data = get_additional_form_data(int(f_num))
                all_data = {**all_data, **additional_data}
                
                if subject_name:
                    matched = {}
                    for name, data in all_data.items():
                        if subject_name.lower() in name.lower():
                            matched[name] = data
                    if matched:
                        self.seed_data(matched, f_num)
                    else:
                        self.stdout.write(f"  ⏭️  '{subject_name}' not in {display_name}")
                else:
                    self.seed_data(all_data, f_num)

    def list_subjects(self):
        all_syllabi = [
            ('1', 'Form 1', FORM_1_SYLLABUS),
            ('2', 'Form 2', FORM_2_SYLLABUS),
            ('3', 'Form 3', FORM_3_SYLLABUS),
            ('4', 'Form 4', FORM_4_SYLLABUS),
        ]
        for f_num, f_name, syllabus_data in all_syllabi:
            # Merge additional subjects
            additional = get_additional_form_data(int(f_num))
            merged = {**syllabus_data, **additional}
            self.stdout.write(f"\n📚 {f_name}:")
            for name in merged.keys():
                topics_count = len(merged[name]['topics'])
                subtopics_count = sum(
                    len(t.get('subtopics', [])) for t in merged[name]['topics']
                )
                self.stdout.write(f"  • {name}: {topics_count} topics, {subtopics_count} subtopics")

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
