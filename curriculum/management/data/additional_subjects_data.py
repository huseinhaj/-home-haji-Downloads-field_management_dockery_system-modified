"""
Additional O-Level syllabus subjects data (Forms 1-4).
Imported by curriculum/management/commands/seed_tie_syllabus.py
to merge into the main syllabus data.

Subjects included:
  - Historia ya Tanzania na Maadili
  - Computer Science
  - Business Studies
  - Commerce
  - Book-Keeping
  - Agriculture
"""

ADDITIONAL_SUBJECTS = {
    "Historia ya Tanzania na Maadili": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "Dhana ya Historia ya Tanzania na Maadili", "order": 1, "subtopics": [
                "Maana ya historia na maadili",
                "Umuhimu wa kujifunza historia ya Tanzania na maadili",
                "Vyanzo vya historia",
                "Uhusiano kati ya historia na maadili",
            ]},
            {"name": "Chimbuko la Jamii za Kitanzania na Maadili Yake", "order": 2, "subtopics": [
                "Nadharia za chimbuko la jamii",
                "Uhamiaji na makazi ya jamii za Kitanzania",
                "Maadili asilia ya jamii za Kitanzania",
            ]},
            {"name": "Maadili na Urithi wa Jamii za Kitanzania", "order": 3, "subtopics": [
                "Dhana ya maadili na urithi",
                "Aina za maadili katika jamii za Kitanzania",
                "Urithi wa kihistoria na kitamaduni",
                "Hifadhi ya urithi wa Kitanzania",
            ]},
            {"name": "Fursa Zitokanazo na Urithi wa Kihistoria wa Tanzania", "order": 4, "subtopics": [
                "Utalii wa kihistoria",
                "Vivutio vya kihistoria nchini Tanzania",
                "Utumiaji wa urithi kwa maendeleo ya uchumi",
            ]},
            {"name": "Mifumo katika Jamii za Kitanzania Kabla ya Ukoloni", "order": 5, "subtopics": [
                "Mifumo ya kisiasa kabla ya ukoloni",
                "Mifumo ya kijamii na kiuchumi",
                "Mfumo wa ukoo na kabila",
                "Mfumo wa Ntemi na machifu",
            ]},
            {"name": "Uhusiano kati ya Jamii za Kitanzania na Jamii Nyingine", "order": 6, "subtopics": [
                "Biashara kati ya jamii za Kitanzania na jamii za nje",
                "Uhamiaji na mwingiliano wa jamii",
                "Athari za uhusiano wa kimataifa kabla ya ukoloni",
            ]},
            {"name": "Sayansi na Teknolojia Kabla ya Ukoloni", "order": 7, "subtopics": [
                "Maendeleo ya sayansi na teknolojia kabla ya ukoloni",
                "Teknolojia ya uchimbaji madini na kuyeyusha madini",
                "Teknolojia ya kilimo na ufugaji",
                "Uhandisi na usanifu wa majengo",
            ]},
        ],
        "form_2": [
            {"name": "Ukoloni Katika Jamii za Kitanzania", "order": 1, "subtopics": [
                "Dhana ya ukoloni",
                "Mikakati ya kuanzishwa kwa ukoloni",
                "Ugawaji wa Afrika (Berlin Conference 1884/85)",
                "Kuanzishwa kwa utawala wa kikoloni Tanzania",
            ]},
            {"name": "Athari za Ukoloni Katika Jamii ya Kitanzania", "order": 2, "subtopics": [
                "Athari za kisiasa za ukoloni",
                "Athari za kiuchumi za ukoloni",
                "Athari za kijamii na kitamaduni",
                "Mabadiliko ya maadili wakati wa ukoloni",
            ]},
            {"name": "Mapambano ya Kudai Uhuru wa Tanganyika na Zanzibar", "order": 3, "subtopics": [
                "Vyanzo vya harakati za uhuru",
                "Harakati za kisiasa Tanganyika (TANU)",
                "Harakati za kisiasa Zanzibar (ASP)",
                "Wahusika muhimu katika harakati za uhuru",
                "Upataji wa uhuru (1961 na 1963)",
            ]},
        ],
        "form_3": [
            {"name": "Harakati za Umoja wa Afrika na Ukombozi", "order": 1, "subtopics": [
                "Dhana ya ukombozi wa Afrika",
                "Umoja wa Afrika (OAU) na dhima yake",
                "Jukumu la Tanzania katika ukombozi wa Afrika",
                "Mchango wa Mwalimu Nyerere katika ukombozi",
            ]},
            {"name": "Ujenzi wa Taifa na Utawala Bora", "order": 2, "subtopics": [
                "Dhana ya ujenzi wa taifa",
                "Sera za maendeleo baada ya uhuru",
                "Azimio la Arusha na Ujamaa",
                "Muungano wa Tanganyika na Zanzibar",
                "Misingi ya utawala bora",
            ]},
            {"name": "Maadili na Wajibu wa Raia Katika Maendeleo ya Taifa", "order": 3, "subtopics": [
                "Dhana ya maadili ya uraia",
                "Wajibu wa raia kwa taifa",
                "Haki za binadamu na wajibu",
                "Kushiriki katika demokrasia na maendeleo",
            ]},
        ],
        "form_4": [
            {"name": "Changamoto za Maendeleo ya Taifa", "order": 1, "subtopics": [
                "Changamoto za kisiasa",
                "Changamoto za kiuchumi",
                "Changamoto za kijamii na kitamaduni",
                "Mikakati ya kukabiliana na changamoto",
            ]},
            {"name": "Sera na Mikakati ya Maendeleo ya Tanzania", "order": 2, "subtopics": [
                "Sera za maendeleo ya uchumi (Vision 2025, MKUKUTA)",
                "Sera za elimu na afya",
                "Sera za kijamii na utamaduni",
                "Tathmini ya sera za maendeleo",
            ]},
            {"name": "Tanzania Katika Ulimwengu wa Kimataifa", "order": 3, "subtopics": [
                "Sera ya kigeni ya Tanzania",
                "Ushiriki wa Tanzania katika mashirika ya kimataifa",
                "Diplomasia na ushirikiano wa kimataifa",
                "Tanzania katika uchumi wa dunia",
            ]},
            {"name": "Maadili Katika Maendeleo Endelevu", "order": 4, "subtopics": [
                "Maadili ya mazingira",
                "Maadili ya kazi na uzalishaji",
                "Maadili ya utawala na uongozi",
                "Maadili ya teknolojia na uvumbuzi",
            ]},
        ],
    },
    "Computer Science": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "Introduction to Computer Science", "order": 1, "subtopics": [
                "Meaning of Computer Science",
                "History and generations of computers",
                "Importance of Computer Science in daily life",
                "Impact of ICT on society",
            ]},
            {"name": "Computer Systems", "order": 2, "subtopics": [
                "Hardware components",
                "Input, output and storage devices",
                "System software and application software",
                "Operating systems",
            ]},
            {"name": "Data Management", "order": 3, "subtopics": [
                "Data and information concepts",
                "Data entry, storage and processing",
                "File management",
            ]},
            {"name": "Networking and Telecommunications", "order": 4, "subtopics": [
                "Basics of computer networks",
                "The internet and World Wide Web",
                "Email communication",
                "Network security and safe browsing",
            ]},
            {"name": "Productivity and Application Software", "order": 5, "subtopics": [
                "Word processing",
                "Spreadsheet basics",
                "Presentation software",
                "Database basics",
            ]},
        ],
        "form_2": [
            {"name": "Networking and Telecommunication Systems", "order": 1, "subtopics": [
                "Types of networks (LAN, WAN, MAN)",
                "Network topologies",
                "Network devices",
                "Internet protocols and services",
            ]},
            {"name": "Ethical and Social Issues in ICT", "order": 2, "subtopics": [
                "Digital citizenship",
                "Copyright and intellectual property",
                "Cyber security and privacy",
                "Social media ethics",
            ]},
            {"name": "Computer Maintenance and Repair", "order": 3, "subtopics": [
                "Hardware maintenance",
                "Software maintenance",
                "Basic troubleshooting techniques",
                "Preventive maintenance",
            ]},
            {"name": "Data Representation and Processing", "order": 4, "subtopics": [
                "Number systems (binary, decimal, hexadecimal)",
                "Data encoding",
                "Data storage units",
            ]},
        ],
        "form_3": [
            {"name": "Programming Fundamentals", "order": 1, "subtopics": [
                "Introduction to programming",
                "Algorithms and flowcharts",
                "Programming languages",
                "Introduction to Python or equivalent",
            ]},
            {"name": "Database Management", "order": 2, "subtopics": [
                "Database concepts",
                "Creating and managing databases",
                "Database querying (SQL basics)",
            ]},
            {"name": "Web Technologies", "order": 3, "subtopics": [
                "HTML and web page structure",
                "CSS for styling",
                "Introduction to web design",
                "Website development project",
            ]},
        ],
        "form_4": [
            {"name": "System Analysis and Design", "order": 1, "subtopics": [
                "Systems development life cycle",
                "Feasibility study",
                "System design and implementation",
            ]},
            {"name": "Advanced Programming Concepts", "order": 2, "subtopics": [
                "Data structures",
                "Object-oriented programming concepts",
                "Software testing and debugging",
            ]},
            {"name": "Information Systems in Society", "order": 3, "subtopics": [
                "Types of information systems",
                "E-government and e-commerce",
                "ICT in business and development",
            ]},
            {"name": "Project Work", "order": 4, "subtopics": [
                "Project planning and proposal",
                "Project development and implementation",
                "Project presentation and evaluation",
            ]},
        ],
    },
    "Business Studies": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "Introduction to Business Studies", "order": 1, "subtopics": [
                "Meaning of Business Studies",
                "Business activities (production, distribution, exchange, consumption)",
                "Importance of Business Studies",
            ]},
            {"name": "Entrepreneurship", "order": 2, "subtopics": [
                "Meaning of entrepreneurship and entrepreneur",
                "Characteristics of an entrepreneur",
                "Role of entrepreneurs in economic development",
            ]},
            {"name": "Sole Proprietorship", "order": 3, "subtopics": [
                "Meaning of sole proprietorship",
                "Characteristics of sole proprietorship",
                "Advantages and disadvantages",
                "Formation and registration",
            ]},
        ],
        "form_2": [
            {"name": "Partnership", "order": 1, "subtopics": [
                "Meaning and characteristics of partnership",
                "Types of partners",
                "Partnership agreement",
                "Advantages and disadvantages",
            ]},
            {"name": "Company Formation", "order": 2, "subtopics": [
                "Meaning and types of companies",
                "Formation procedures",
                "Memorandum and Articles of Association",
                "Advantages and disadvantages",
            ]},
            {"name": "Business Communication", "order": 3, "subtopics": [
                "Meaning and importance of business communication",
                "Types and channels of communication",
                "Barriers to effective communication",
            ]},
        ],
        "form_3": [
            {"name": "Marketing", "order": 1, "subtopics": [
                "Meaning and importance of marketing",
                "Marketing mix (4Ps)",
                "Market research",
                "Promotion and advertising",
            ]},
            {"name": "Business Finance", "order": 2, "subtopics": [
                "Sources of business finance",
                "Short-term and long-term financing",
                "Financial institutions",
            ]},
            {"name": "Business Calculations", "order": 3, "subtopics": [
                "Profit and loss",
                "Pricing strategies",
                "Break-even analysis",
                "Simple business ratios",
            ]},
        ],
        "form_4": [
            {"name": "Business Management", "order": 1, "subtopics": [
                "Functions of management",
                "Organizational structure",
                "Leadership and motivation",
                "Human resource management",
            ]},
            {"name": "Taxation", "order": 2, "subtopics": [
                "Meaning and importance of taxation",
                "Types of taxes",
                "Tax administration in Tanzania",
            ]},
            {"name": "International Trade", "order": 3, "subtopics": [
                "Meaning and importance of international trade",
                "Balance of trade and balance of payments",
                "Trade restrictions and protections",
                "Regional economic integration (EAC, SADC)",
            ]},
        ],
    },
    "Commerce": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "The Basics of Commerce", "order": 1, "subtopics": [
                "Meaning and elements of commerce",
                "Nature of goods and services",
                "Evolution and growth of commerce",
                "Barter trade and its limitations",
            ]},
            {"name": "Production", "order": 2, "subtopics": [
                "Meaning of production",
                "Factors of production and their rewards",
                "Stages of production",
                "Needs and wants",
            ]},
            {"name": "Entrepreneurship", "order": 3, "subtopics": [
                "Concept of entrepreneurship",
                "Characteristics of an entrepreneur",
                "Business opportunities",
                "Self-employment",
            ]},
            {"name": "Domestic Trade", "order": 4, "subtopics": [
                "Retail trade",
                "Wholesale trade",
                "Channels of distribution",
            ]},
        ],
        "form_2": [
            {"name": "Foreign Trade", "order": 1, "subtopics": [
                "Meaning and importance of foreign trade",
                "Export and import procedures",
                "Balance of trade",
            ]},
            {"name": "Transport", "order": 2, "subtopics": [
                "Meaning and importance of transport",
                "Modes of transport",
                "Factors influencing choice of transport",
                "Documents used in transport",
            ]},
            {"name": "Insurance", "order": 3, "subtopics": [
                "Meaning and principles of insurance",
                "Types of insurance",
                "Insurance contract and documents",
            ]},
            {"name": "Warehousing", "order": 4, "subtopics": [
                "Meaning and importance of warehousing",
                "Types of warehouses",
                "Warehousing documents",
            ]},
        ],
        "form_3": [
            {"name": "Banking", "order": 1, "subtopics": [
                "Meaning and functions of banks",
                "Types of banks",
                "Bank accounts",
                "Banking services and documents",
            ]},
            {"name": "Communication", "order": 2, "subtopics": [
                "Meaning and importance of business communication",
                "Modes of communication",
                "Modern communication technology in business",
            ]},
            {"name": "Advertising", "order": 3, "subtopics": [
                "Meaning and importance of advertising",
                "Types of advertising",
                "Advertising media",
                "Advertising effectiveness",
            ]},
            {"name": "Market Research", "order": 4, "subtopics": [
                "Meaning and importance of market research",
                "Methods of data collection",
                "Market research process",
            ]},
        ],
        "form_4": [
            {"name": "Business Finance", "order": 1, "subtopics": [
                "Sources of capital",
                "Capital and revenue expenditure",
                "Financial management",
            ]},
            {"name": "Taxation", "order": 2, "subtopics": [
                "Principles of taxation",
                "Types of taxes in Tanzania",
                "Tax administration and collection",
            ]},
            {"name": "Economic Development", "order": 3, "subtopics": [
                "Meaning and indicators of economic development",
                "Role of commerce in economic development",
                "Development plans in Tanzania",
            ]},
            {"name": "Consumer Protection", "order": 4, "subtopics": [
                "Meaning and importance of consumer protection",
                "Consumer rights and responsibilities",
                "Consumer protection agencies in Tanzania",
            ]},
        ],
    },
    "Book-Keeping": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "Introduction to Book-Keeping", "order": 1, "subtopics": [
                "Meaning and concept of book-keeping",
                "Relationship with other subjects",
                "Importance of book-keeping",
                "Accounting cycle and process",
                "Basic book-keeping terms",
            ]},
            {"name": "Principles of Double Entry", "order": 2, "subtopics": [
                "The accounting equation",
                "Statement of affairs",
                "Golden rules of double entry",
                "Importance of double entry",
            ]},
            {"name": "Books of Prime Entry", "order": 3, "subtopics": [
                "Meaning and types of books of prime entry",
                "Source documents",
                "Preparation of books of prime entry",
            ]},
            {"name": "Ledgers", "order": 4, "subtopics": [
                "Meaning and format of a ledger",
                "Types of ledgers",
                "Classification of accounts",
                "Posting entries and balancing accounts",
            ]},
            {"name": "Trial Balance", "order": 5, "subtopics": [
                "Meaning and purpose of a trial balance",
                "Preparation of a trial balance",
                "Advantages and limitations",
            ]},
            {"name": "Elementary Financial Statements", "order": 6, "subtopics": [
                "Purpose of financial statements",
                "Users of financial statements",
                "Income statement",
                "Statement of financial position",
            ]},
        ],
        "form_2": [
            {"name": "Correction of Errors", "order": 1, "subtopics": [
                "Types of errors",
                "Suspense account",
                "Rectifying entries",
                "Effects of errors on profit",
            ]},
            {"name": "Bank Reconciliation", "order": 2, "subtopics": [
                "Bank statement vs cash book",
                "Reasons for differences",
                "Preparation of bank reconciliation statement",
            ]},
            {"name": "Control Accounts", "order": 3, "subtopics": [
                "Meaning and purpose of control accounts",
                "Sales ledger control account",
                "Purchases ledger control account",
            ]},
            {"name": "Departmental Accounts", "order": 4, "subtopics": [
                "Meaning of departmental accounts",
                "Apportionment of expenses",
                "Departmental trading and profit & loss account",
            ]},
        ],
        "form_3": [
            {"name": "Depreciation", "order": 1, "subtopics": [
                "Meaning and causes of depreciation",
                "Methods of calculating depreciation",
                "Accounting for depreciation",
                "Disposal of fixed assets",
            ]},
            {"name": "Final Accounts for Sole Traders", "order": 2, "subtopics": [
                "Trading account",
                "Profit and loss account",
                "Balance sheet",
                "Adjustments (accruals, prepayments, bad debts)",
            ]},
            {"name": "Incomplete Records", "order": 3, "subtopics": [
                "Meaning of incomplete records",
                "Determining profit from incomplete records",
                "Statement of affairs method",
            ]},
        ],
        "form_4": [
            {"name": "Partnership Accounts", "order": 1, "subtopics": [
                "Partnership agreement and capital accounts",
                "Profit and loss appropriation account",
                "Current accounts and drawings",
                "Admission and retirement of partners",
            ]},
            {"name": "Company Accounts", "order": 2, "subtopics": [
                "Share capital and reserves",
                "Debentures and loan capital",
                "Company final accounts",
                "Dividends and retained earnings",
            ]},
            {"name": "Interpretation of Accounts", "order": 3, "subtopics": [
                "Financial ratios",
                "Liquidity ratios",
                "Profitability ratios",
                "Efficiency ratios",
            ]},
            {"name": "Manufacturing Accounts", "order": 4, "subtopics": [
                "Manufacturing account format",
                "Cost classification",
                "Valuation of work in progress",
            ]},
        ],
    },
    "Agriculture": {
        "subject_code": "secondary",
        "form_1": [
            {"name": "Introduction to Agriculture", "order": 1, "subtopics": [
                "Meaning and importance of agriculture",
                "Branches of agriculture",
                "Role of agriculture in Tanzanian economy",
            ]},
            {"name": "Crop Production", "order": 2, "subtopics": [
                "Classification of crops",
                "General practices in crop production",
                "Importance of crop production",
            ]},
            {"name": "Cropping Systems and Patterns", "order": 3, "subtopics": [
                "Types of cropping systems",
                "Cropping patterns",
                "Advantages and disadvantages",
            ]},
            {"name": "Introduction to Livestock Production", "order": 4, "subtopics": [
                "Meaning of livestock production",
                "Classification of livestock",
                "Importance of livestock production",
            ]},
            {"name": "Livestock Breeds", "order": 5, "subtopics": [
                "Breeds of cattle",
                "Breeds of poultry",
                "Breeds of pigs and goats",
            ]},
            {"name": "Livestock Farming Systems", "order": 6, "subtopics": [
                "Meaning of livestock farming systems",
                "Types of farming systems",
                "Intensive and extensive systems",
            ]},
            {"name": "Introduction to Mechanisation in Agriculture", "order": 7, "subtopics": [
                "Meaning of mechanisation",
                "Importance of mechanisation",
                "Mechanized farm activities",
            ]},
            {"name": "Farm Tools and Equipment", "order": 8, "subtopics": [
                "Hand tools and their uses",
                "Proper handling of farm tools",
                "Storage and maintenance",
            ]},
            {"name": "Farm Workshop", "order": 9, "subtopics": [
                "Meaning and purpose of a farm workshop",
                "Workshop tools and equipment",
                "Safety precautions in the workshop",
            ]},
            {"name": "Farm Machinery", "order": 10, "subtopics": [
                "Common farm machines",
                "Care and maintenance of machines",
                "Selection of farm machinery",
            ]},
            {"name": "Farm Power", "order": 11, "subtopics": [
                "Meaning and sources of farm power",
                "Human power",
                "Animal power",
                "Mechanical and electrical power",
            ]},
            {"name": "The Concept of Soil", "order": 12, "subtopics": [
                "Meaning of soil",
                "Soil constituents",
                "Soil formation process",
                "Soil horizons",
            ]},
            {"name": "Physical Properties of Soil", "order": 13, "subtopics": [
                "Soil texture",
                "Soil structure",
                "Soil porosity",
                "Soil colour",
            ]},
        ],
        "form_2": [
            {"name": "Soil Fertility", "order": 1, "subtopics": [
                "Meaning of soil fertility",
                "Plant nutrients and their functions",
                "Methods of maintaining soil fertility",
                "Organic and inorganic fertilizers",
            ]},
            {"name": "Water and Irrigation", "order": 2, "subtopics": [
                "Importance of water in agriculture",
                "Sources of water",
                "Irrigation methods and systems",
                "Drainage systems",
            ]},
            {"name": "Crop Pests and Diseases", "order": 3, "subtopics": [
                "Meaning of crop pests",
                "Types of crop pests",
                "Crop diseases and their control",
                "Integrated pest management",
            ]},
            {"name": "Farm Economics", "order": 4, "subtopics": [
                "Meaning of farm economics",
                "Farm records and accounts",
                "Cost-benefit analysis",
                "Farm planning and budgeting",
            ]},
        ],
        "form_3": [
            {"name": "Livestock Production and Management", "order": 1, "subtopics": [
                "Animal nutrition and feeding",
                "Animal health and diseases",
                "Animal reproduction and breeding",
                "Livestock housing and equipment",
            ]},
            {"name": "Crop Production II", "order": 2, "subtopics": [
                "Field crop production practices",
                "Horticultural crop production",
                "Harvesting and post-harvest handling",
                "Storage and marketing of crops",
            ]},
            {"name": "Farm Planning and Management", "order": 3, "subtopics": [
                "Meaning of farm planning",
                "Types of farm plans",
                "Farm management principles",
                "Decision making in farming",
            ]},
        ],
        "form_4": [
            {"name": "Agricultural Marketing", "order": 1, "subtopics": [
                "Meaning and importance of agricultural marketing",
                "Marketing channels and systems",
                "Price determination",
                "Agricultural cooperatives",
            ]},
            {"name": "Farm Business Management", "order": 2, "subtopics": [
                "Farm business analysis",
                "Capital and credit in agriculture",
                "Agricultural insurance",
                "Risk management in farming",
            ]},
            {"name": "Agricultural Policy and Development", "order": 3, "subtopics": [
                "Agricultural policy in Tanzania",
                "Agricultural extension services",
                "Role of agriculture in national development",
                "Sustainable agriculture",
            ]},
        ],
    },
}


def get_additional_form_data(form_number):
    """
    Get additional subjects data merged into the standard format
    {subject_name: {subject_code, topics: [...]}} for a given form.
    """
    form_key = f"form_{form_number}"
    result = {}
    for subject_name, data in ADDITIONAL_SUBJECTS.items():
        topics = data.get(form_key, [])
        if topics:
            result[subject_name] = {
                "subject_code": data["subject_code"],
                "topics": topics,
            }
    return result
