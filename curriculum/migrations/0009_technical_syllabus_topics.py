"""
Data migration: Masomo ya ufundi (VETA/Technical) — topics na subtopics.
Sawa na seed_primary_syllabus — kila somo lina topics na subtopics kwa kila
darasa la VETA (Grade III, Grade II, Grade I, NTA 4/5/6).
Inatekelezwa kiotomatiki wakati wa 'manage.py migrate'.
"""
from django.db import migrations


TECHNICAL_CLASSES = [
    'Grade III',
    'Grade II',
    'Grade I',
    'NTA 4 (Basic Certificate)',
    'NTA 5 (Certificate)',
    'NTA 6 (Diploma)',
]

TECHNICAL_SYLLABUS = {
    "Electrical Installation": {
        "code": "T01",
        "topics": [
            {"name": "Introduction to Electrical Installation", "subtopics": [
                "Meaning and importance of electrical installation",
                "Electrical safety rules and regulations",
                "Tools and equipment for electrical installation",
                "Personal protective equipment (PPE)",
                "Care and maintenance of tools",
            ]},
            {"name": "Electrical Circuits and Symbols", "subtopics": [
                "Basic electrical quantities (voltage, current, resistance, power)",
                "Ohm's law and power formula",
                "Electrical circuit diagrams and symbols",
                "Series and parallel circuits",
                "Conductors, insulators and semi-conductors",
            ]},
            {"name": "Cables, Wiring and Conduits", "subtopics": [
                "Types and sizes of cables",
                "Selection of cables for domestic installations",
                "Conduit and trunking installation",
                "Cable jointing and termination",
                "Colour coding of wires",
            ]},
            {"name": "Lighting and Socket Installation", "subtopics": [
                "Types of lamps and lighting circuits",
                "Two-way and intermediate switching",
                "Socket outlets and power circuits",
                "Connecting ceiling roses and lamps",
                "Testing lighting circuits",
            ]},
            {"name": "Earthing and Protection", "subtopics": [
                "Purpose and types of earthing systems",
                "Earth electrodes and earth conductors",
                "Fuses, circuit breakers and RCDs",
                "Surge protection",
                "Testing and measuring earth resistance",
            ]},
            {"name": "Distribution Boards and Meters", "subtopics": [
                "Main switch and distribution board layout",
                "Connecting sub-circuits",
                "Electric meters and meter reading",
                "Load balancing",
                "Inspection and testing of installations",
            ]},
            {"name": "Domestic Installation Projects", "subtopics": [
                "Reading architectural plans for wiring",
                "Estimating materials and costs",
                "Wiring a complete house (practical project)",
                "Final inspection and commissioning",
                "Fault finding and rectification",
            ]},
            {"name": "Industrial and Commercial Installations", "subtopics": [
                "Three-phase supply basics",
                "Motor control circuits",
                "Sub-distribution and panel wiring",
                "Emergency and security lighting",
                "Maintenance of industrial installations",
            ]},
        ]
    },
    "Electrical Engineering": {
        "code": "T02",
        "topics": [
            {"name": "Electrical Principles", "subtopics": [
                "D.C. and A.C. theory",
                "Magnetism and electromagnetism",
                "Capacitance and inductance",
                "Power factor and energy",
                "Electrical machines overview",
            ]},
            {"name": "D.C. Machines", "subtopics": [
                "Construction of D.C. motors and generators",
                "Principles of operation",
                "Speed control of D.C. motors",
                "Testing and maintenance",
                "Fault diagnosis and repair",
            ]},
            {"name": "A.C. Machines", "subtopics": [
                "Single-phase and three-phase induction motors",
                "Alternators and transformers",
                "Starting methods for A.C. motors",
                "Protection of machines",
                "Maintenance and rewinding basics",
            ]},
            {"name": "Transformers", "subtopics": [
                "Transformer construction and principle",
                "Transformer losses and efficiency",
                "Testing transformers",
                "Distribution transformers",
                "Transformer maintenance",
            ]},
            {"name": "Electrical Measurements", "subtopics": [
                "Measurement of current, voltage, resistance",
                "Wattmeters and energy meters",
                "Megger and earth testing",
                "Cathode ray oscilloscope basics",
                "Calibration and errors",
            ]},
            {"name": "Power Generation and Distribution", "subtopics": [
                "Sources of electrical energy",
                "Generation, transmission and distribution",
                "Substations and switchgear",
                "Load characteristics",
                "Energy efficiency and conservation",
            ]},
        ]
    },
    "Electronics and Communication": {
        "code": "T03",
        "topics": [
            {"name": "Electronic Components", "subtopics": [
                "Resistors, capacitors, inductors",
                "Diodes, transistors and ICs",
                "Sensors and transducers",
                "Component identification and testing",
                "Soldering and de-soldering techniques",
            ]},
            {"name": "Semiconductor Devices", "subtopics": [
                "PN junction and diode characteristics",
                "Rectifier circuits (half-wave, full-wave, bridge)",
                "Transistor biasing and amplifiers",
                "Voltage regulators",
                "Optoelectronic devices (LED, photodiode)",
            ]},
            {"name": "Digital Electronics", "subtopics": [
                "Number systems (binary, octal, hex)",
                "Logic gates and truth tables",
                "Combinational logic circuits",
                "Flip-flops and counters",
                "Introduction to microprocessors",
            ]},
            {"name": "Communication Systems", "subtopics": [
                "Principles of communication",
                "Amplitude and frequency modulation",
                "Radio transmitters and receivers",
                "Mobile and wireless communication basics",
                "Antennas and propagation",
            ]},
            {"name": "Audio and Video Equipment", "subtopics": [
                "Audio amplifiers",
                "Loudspeakers and microphones",
                "Radio and TV receiver basics",
                "DVD/MP3 player repair",
                "Fault finding in electronic equipment",
            ]},
            {"name": "Electronic Project Work", "subtopics": [
                "Designing simple electronic circuits",
                "PCB design and fabrication",
                "Assembling and testing projects",
                "Interfacing sensors with circuits",
                "Documenting and presenting projects",
            ]},
        ]
    },
    "Plumbing and Pipe Fitting": {
        "code": "T04",
        "topics": [
            {"name": "Introduction to Plumbing", "subtopics": [
                "Meaning and importance of plumbing",
                "Plumbing tools and equipment",
                "Materials used in plumbing (PVC, GI, copper, PPR)",
                "Safety precautions in plumbing",
                "Reading plumbing drawings",
            ]},
            {"name": "Pipes and Pipe Fittings", "subtopics": [
                "Types and sizes of pipes",
                "Pipe fittings and their uses",
                "Cutting, threading and bending pipes",
                "Joining pipes (solvent, compression, threaded)",
                "Testing joints for leaks",
            ]},
            {"name": "Water Supply Systems", "subtopics": [
                "Sources of water and treatment",
                "Cold and hot water supply systems",
                "Storage tanks and cisterns",
                "Pumps and pressure systems",
                "Pipe sizing and layout",
            ]},
            {"name": "Sanitary Appliances", "subtopics": [
                "Wash basins, sinks and bathtubs",
                "Water closets and flushing systems",
                "Urinals and shower fittings",
                "Installation of sanitary appliances",
                "Testing and commissioning sanitary installations",
            ]},
            {"name": "Drainage and Sewerage", "subtopics": [
                "Principles of drainage",
                "Soil, waste and vent pipes",
                "Traps and inspection chambers",
                "Septic tanks and soakaways",
                "Drain testing and maintenance",
            ]},
            {"name": "Practical Plumbing Projects", "subtopics": [
                "Installing a complete bathroom",
                "Installing a kitchen sink unit",
                "Repairing burst pipes and leaks",
                "Maintenance of plumbing systems",
                "Estimating plumbing materials and costs",
            ]},
        ]
    },
    "Masonry and Brick Laying": {
        "code": "T05",
        "topics": [
            {"name": "Introduction to Masonry", "subtopics": [
                "Meaning and importance of masonry",
                "Masonry tools and equipment",
                "Materials: blocks, bricks, mortar, cement",
                "Safety in masonry works",
                "Setting out the worksite",
            ]},
            {"name": "Mortar and Concrete Mixing", "subtopics": [
                "Types of mortar and their uses",
                "Mix ratios and water-cement ratio",
                "Mixing by hand and machine",
                "Testing mortar consistency",
                "Curing of concrete and mortar",
            ]},
            {"name": "Brick and Block Laying", "subtopics": [
                "Bonding patterns (English, Flemish, Stretcher)",
                "Laying bricks and blocks to line and level",
                "Construction of walls, corners and openings",
                "Lintels and beams",
                "Pointing and finishing joints",
            ]},
            {"name": "Concrete Work", "subtopics": [
                "Concrete mix design",
                "Formwork construction",
                "Reinforcement basics",
                "Placing and compacting concrete",
                "Slabs, columns and footings",
            ]},
            {"name": "Plastering and Rendering", "subtopics": [
                "Preparation of surfaces",
                "Plaster mixes and application",
                "Internal and external rendering",
                "Screeding floors",
                "Repairing cracks and defects",
            ]},
            {"name": "Construction Projects", "subtopics": [
                "Building a small structure (practical)",
                "Estimating quantities of materials",
                "Reading simple construction drawings",
                "Quality control and inspection",
                "Site organisation and safety",
            ]},
        ]
    },
    "Carpentry and Joinery": {
        "code": "T06",
        "topics": [
            {"name": "Introduction to Carpentry", "subtopics": [
                "Meaning and importance of carpentry",
                "Carpentry tools and their uses",
                "Timber: types, seasoning and preservation",
                "Safety in the workshop",
                "Care and maintenance of tools",
            ]},
            {"name": "Timber Measurements and Marking", "subtopics": [
                "Measuring and marking out",
                "Squaring and setting out joints",
                "Sawing techniques",
                "Planing and shaping timber",
                "Reading workshop drawings",
            ]},
            {"name": "Joints and Joinery", "subtopics": [
                "Butt, lap and halved joints",
                "Mortise and tenon joints",
                "Dovetail joints",
                "Bridle and housing joints",
                "Choosing the right joint",
            ]},
            {"name": "Doors, Windows and Frames", "subtopics": [
                "Construction of panelled doors",
                "Framed ledged and braced doors",
                "Windows and casement construction",
                "Hanging doors and fitting locks",
                "Fixing frames into walls",
            ]},
            {"name": "Furniture Making", "subtopics": [
                "Tables, chairs and stools",
                "Cabinets, shelves and cupboards",
                "Bed frames",
                "Using manufactured boards (plywood, MDF)",
                "Finishing and polishing furniture",
            ]},
            {"name": "Workshop Practice and Projects", "subtopics": [
                "Workshop safety and housekeeping",
                "Estimating timber requirements",
                "Making a complete piece of furniture (project)",
                "Repairing and renovating furniture",
                "Quality inspection and finishing",
            ]},
        ]
    },
    "Welding and Metal Fabrication": {
        "code": "T07",
        "topics": [
            {"name": "Introduction to Welding", "subtopics": [
                "Meaning and importance of welding",
                "Types of welding (arc, gas, TIG, MIG)",
                "Welding tools and equipment",
                "Safety in welding (burns, fumes, eye protection)",
                "Personal protective equipment",
            ]},
            {"name": "Welding Equipment and Settings", "subtopics": [
                "Arc welding machines",
                "Electrodes: types and selection",
                "Setting current and polarity",
                "Gas welding equipment and regulators",
                "Care and maintenance of equipment",
            ]},
            {"name": "Welding Techniques", "subtopics": [
                "Preparing metal surfaces",
                "Striking and maintaining the arc",
                "Beads, runs and weaving",
                "Butt, lap, T and corner joints",
                "Positional welding (flat, vertical, overhead)",
            ]},
            {"name": "Gas Welding and Cutting", "subtopics": [
                "Oxy-acetylene welding",
                "Flame types and adjustment",
                "Brazing and soldering",
                "Oxy-fuel cutting",
                "Safety with gas cylinders",
            ]},
            {"name": "Metal Fabrication", "subtopics": [
                "Marking out and cutting metal",
                "Bending and forming",
                "Frames and structures",
                "Gates, windows and steel furniture",
                "Reading fabrication drawings",
            ]},
            {"name": "Inspection and Quality Control", "subtopics": [
                "Weld defects and causes",
                "Inspection methods",
                "Repairing defective welds",
                "Estimating material and costs",
                "Fabrication project (practical)",
            ]},
        ]
    },
    "Motor Vehicle Mechanics": {
        "code": "T08",
        "topics": [
            {"name": "Introduction to Motor Vehicles", "subtopics": [
                "Parts of a motor vehicle",
                "Vehicle identification and specifications",
                "Workshop safety and housekeeping",
                "Workshop tools and equipment",
                "Lubricants and their uses",
            ]},
            {"name": "Engine Systems", "subtopics": [
                "Four-stroke and two-stroke engines",
                "Engine components and their functions",
                "Valve timing and clearances",
                "Cooling system",
                "Lubrication system",
            ]},
            {"name": "Fuel and Ignition Systems", "subtopics": [
                "Petrol fuel system (carburettor and injection)",
                "Diesel fuel system (pumps and injectors)",
                "Ignition system components",
                "Electronic engine management basics",
                "Fuel system servicing",
            ]},
            {"name": "Transmission and Drive Line", "subtopics": [
                "Clutch: types and adjustment",
                "Gearboxes and gear selection",
                "Propeller shaft and differential",
                "Final drive and axles",
                "Automatic transmission basics",
            ]},
            {"name": "Braking and Steering Systems", "subtopics": [
                "Hydraulic braking system",
                "Disc and drum brakes",
                "Handbrake and servo systems",
                "Steering geometry and alignment",
                "Power steering",
            ]},
            {"name": "Suspension and Chassis", "subtopics": [
                "Suspension springs and shock absorbers",
                "Wheel alignment and balancing",
                "Tyres: types, wear and maintenance",
                "Chassis and body repair basics",
                "Undercarriage inspection",
            ]},
            {"name": "Vehicle Servicing and Repair", "subtopics": [
                "Routine servicing schedule",
                "Diagnosis of common faults",
                "Engine overhaul procedures",
                "Electrical and starting systems",
                "Road test and final inspection",
            ]},
        ]
    },
    "Motorcycle and Engine Mechanics": {
        "code": "T09",
        "topics": [
            {"name": "Introduction to Motorcycles", "subtopics": [
                "Parts of a motorcycle",
                "Types of motorcycles (boda boda, scooter, off-road)",
                "Tools and equipment for motorcycle repair",
                "Workshop safety",
                "Motorcycle maintenance schedule",
            ]},
            {"name": "Motorcycle Engine", "subtopics": [
                "Single-cylinder engine construction",
                "Four-stroke and two-stroke engines",
                "Piston, rings and cylinder",
                "Valves and camshaft",
                "Engine disassembly and assembly",
            ]},
            {"name": "Fuel and Electrical Systems", "subtopics": [
                "Carburettor: construction, tuning and repair",
                "Fuel tank and fuel lines",
                "Ignition system (CDI, coil, spark plug)",
                "Battery and charging system",
                "Wiring harness and lights",
            ]},
            {"name": "Drive and Braking Systems", "subtopics": [
                "Clutch: types, adjustment and replacement",
                "Chain drive, sprockets and adjustment",
                "Brakes: drum and disc",
                "Brake bleeding and adjustment",
                "Wheels, tyres and spokes",
            ]},
            {"name": "Suspension and Steering", "subtopics": [
                "Front forks and rear shock absorbers",
                "Steering head and handlebars",
                "Frame inspection",
                "Wheel alignment and balance",
                "Riding safety and pre-ride checks",
            ]},
            {"name": "Diagnosis and Repair Practice", "subtopics": [
                "Common faults and symptoms",
                "Using test equipment",
                "Overhauling a complete motorcycle (project)",
                "Estimating repair costs",
                "Customer care and workshop records",
            ]},
        ]
    },
    "Agriculture and Crop Production": {
        "code": "T10",
        "topics": [
            {"name": "Introduction to Agriculture", "subtopics": [
                "Meaning and importance of agriculture",
                "Farming systems in Tanzania",
                "Agricultural zones and crops",
                "Farm tools and equipment",
                "Farm records and planning",
            ]},
            {"name": "Soil Science", "subtopics": [
                "Soil formation and composition",
                "Soil types and properties",
                "Soil fertility and plant nutrients",
                "Soil conservation measures",
                "Soil testing and fertilisers",
            ]},
            {"name": "Crop Production", "subtopics": [
                "Land preparation",
                "Seed selection and planting",
                "Crop spacing and thinning",
                "Weeding and mulching",
                "Irrigation and water management",
            ]},
            {"name": "Crop Protection", "subtopics": [
                "Common pests of crops",
                "Common diseases of crops",
                "Integrated pest management",
                "Safe use of pesticides",
                "Weed control methods",
            ]},
            {"name": "Harvesting and Storage", "subtopics": [
                "Harvesting methods and timing",
                "Post-harvest handling",
                "Storage facilities and grain preservation",
                "Marketing of produce",
                "Value addition basics",
            ]},
            {"name": "Horticulture", "subtopics": [
                "Vegetable production",
                "Fruit tree production",
                "Nursery management",
                "Greenhouse technology",
                "Horticultural marketing",
            ]},
        ]
    },
    "Animal Husbandry": {
        "code": "T11",
        "topics": [
            {"name": "Introduction to Animal Husbandry", "subtopics": [
                "Importance of livestock keeping",
                "Types of livestock in Tanzania",
                "Livestock housing and facilities",
                "Records in livestock production",
                "Livestock welfare",
            ]},
            {"name": "Animal Nutrition", "subtopics": [
                "Nutrients required by animals",
                "Feeds and feed stuffs",
                "Ration formulation",
                "Feeding management",
                "Pasture and fodder production",
            ]},
            {"name": "Animal Breeding", "subtopics": [
                "Breeds of cattle, goats, sheep, pigs, poultry",
                "Selection and mating systems",
                "Reproduction and pregnancy",
                "Calving, lambing and farrowing management",
                "Culling and herd improvement",
            ]},
            {"name": "Animal Health", "subtopics": [
                "Common diseases and their causes",
                "Signs of sick animals",
                "Prevention and control of diseases",
                "Vaccination programmes",
                "Parasite control (internal and external)",
            ]},
            {"name": "Dairy and Meat Production", "subtopics": [
                "Milking techniques and hygiene",
                "Milk handling and processing",
                "Meat production and quality",
                "Fatting and marketing livestock",
                "Value addition of livestock products",
            ]},
            {"name": "Poultry Production", "subtopics": [
                "Broiler and layer production",
                "Incubation and hatching",
                "Brooding and rearing chicks",
                "Poultry health and biosecurity",
                "Egg and poultry marketing",
            ]},
        ]
    },
    "Tailoring and Garment Making": {
        "code": "T12",
        "topics": [
            {"name": "Introduction to Tailoring", "subtopics": [
                "Importance of tailoring and garment making",
                "Sewing tools and equipment",
                "The sewing machine: parts and functions",
                "Threading and operating a sewing machine",
                "Workshop safety and organisation",
            ]},
            {"name": "Body Measurements", "subtopics": [
                "Taking body measurements",
                "Standard measurement charts",
                "Measurement for different garments",
                "Recording and comparing measurements",
                "Adjustments for fit",
            ]},
            {"name": "Pattern Making", "subtopics": [
                "Drafting basic blocks",
                "Patterns for skirts, blouses and trousers",
                "Adapting and manipulating patterns",
                "Grading patterns",
                "Laying patterns on fabric",
            ]},
            {"name": "Cutting and Sewing", "subtopics": [
                "Fabric types and properties",
                "Cutting techniques",
                "Seams and seam finishes",
                "Darts, tucks and gathers",
                "Pockets, collars and sleeves",
            ]},
            {"name": "Garment Construction", "subtopics": [
                "Constructing a skirt",
                "Constructing a blouse/shirt",
                "Constructing trousers",
                "Dresses and children's wear",
                "Fitting and finishing garments",
            ]},
            {"name": "Design and Decoration", "subtopics": [
                "Elements and principles of design",
                "Fashion trends and styles",
                "Embroidery and decorative stitches",
                "Buttons, zips and fasteners",
                "Repair and alteration of garments",
            ]},
        ]
    },
    "Fashion Design and Beauty Therapy": {
        "code": "T13",
        "topics": [
            {"name": "Introduction to Fashion Design", "subtopics": [
                "Meaning of fashion and design",
                "Fashion industry in Tanzania",
                "Fashion illustration basics",
                "Colour theory in fashion",
                "Careers in fashion and beauty",
            ]},
            {"name": "Fashion Illustration", "subtopics": [
                "Drawing fashion figures",
                "Sketching garments",
                "Fabric rendering",
                "Design portfolios",
                "Presenting fashion designs",
            ]},
            {"name": "Garment Design", "subtopics": [
                "Designing for different body types",
                "Designing children's, men's and women's wear",
                "African prints and traditional wear",
                "Uniform and corporate wear design",
                "Sampling and prototyping",
            ]},
            {"name": "Beauty Therapy", "subtopics": [
                "Skin structure and care",
                "Facials and skin treatments",
                "Manicure and pedicure",
                "Makeup application",
                "Beauty products and their uses",
            ]},
            {"name": "Hairdressing", "subtopics": [
                "Hair structure and types",
                "Shampooing and conditioning",
                "Hair styling and setting",
                "Braiding and weaving",
                "Hair treatment and care",
            ]},
            {"name": "Salon and Business Management", "subtopics": [
                "Setting up a salon or fashion business",
                "Customer care and communication",
                "Pricing and record keeping",
                "Health, safety and hygiene in salons",
                "Marketing fashion and beauty services",
            ]},
        ]
    },
    "Catering and Food Production": {
        "code": "T14",
        "topics": [
            {"name": "Introduction to Catering", "subtopics": [
                "Meaning and importance of catering",
                "Catering establishments and services",
                "Kitchen organisation and sections",
                "Kitchen equipment and utensils",
                "Hygiene and food safety",
            ]},
            {"name": "Food Safety and Hygiene", "subtopics": [
                "Personal hygiene of food handlers",
                "Food contamination and prevention",
                "Safe food storage",
                "Foodborne diseases",
                "Kitchen sanitation and waste disposal",
            ]},
            {"name": "Basic Cookery", "subtopics": [
                "Cooking methods (boiling, frying, roasting, steaming)",
                "Vegetable preparation and cooking",
                "Meat, fish and poultry cookery",
                "Sauces, soups and stocks",
                "Egg and cereal dishes",
            ]},
            {"name": "Baking and Pastry", "subtopics": [
                "Baking ingredients and their functions",
                "Bread making",
                "Cakes and sponges",
                "Pastry (short, puff, choux)",
                "Biscuits and confectionery",
            ]},
            {"name": "Menu Planning and Nutrition", "subtopics": [
                "Principles of menu planning",
                "Balanced diets and nutrition",
                "Special dietary needs",
                "Costing and portion control",
                "Writing menus",
            ]},
            {"name": "Food Service", "subtopics": [
                "Types of food service (table, buffet, counter)",
                "Table setting and laying covers",
                "Silver service and plate service",
                "Beverage service",
                "Customer care in food service",
            ]},
        ]
    },
    "Hotel and Tourism Management": {
        "code": "T15",
        "topics": [
            {"name": "Introduction to Hospitality and Tourism", "subtopics": [
                "Meaning of hospitality and tourism",
                "Tourism industry in Tanzania",
                "Types of accommodation",
                "Hotel organisation structure",
                "Careers in hospitality and tourism",
            ]},
            {"name": "Front Office Operations", "subtopics": [
                "Role of the front office",
                "Reservations",
                "Check-in and check-out procedures",
                "Guest accounts and billing",
                "Front office communication",
            ]},
            {"name": "Housekeeping", "subtopics": [
                "Role of the housekeeping department",
                "Cleaning of guest rooms",
                "Linen and laundry management",
                "Public area cleaning",
                "Pest control in hotels",
            ]},
            {"name": "Food and Beverage Service", "subtopics": [
                "Food and beverage outlets",
                "Table service methods",
                "Beverages: non-alcoholic and alcoholic",
                "Bar operations",
                "Room service",
            ]},
            {"name": "Tourism Products and Services", "subtopics": [
                "Tourist attractions in Tanzania",
                "Tour operations and guiding",
                "Travel agency operations",
                "Tourism marketing and promotion",
                "Cultural and eco-tourism",
            ]},
            {"name": "Customer Care and Business Skills", "subtopics": [
                "Guest relations and service excellence",
                "Handling complaints",
                "Communication skills",
                "Sales and marketing in hospitality",
                "Small business management in tourism",
            ]},
        ]
    },
    "Information and Communication Technology": {
        "code": "T16",
        "topics": [
            {"name": "Introduction to ICT", "subtopics": [
                "Meaning and importance of ICT",
                "Computer hardware components",
                "Computer software (system and application)",
                "Types of computers",
                "ICT careers",
            ]},
            {"name": "Operating Systems", "subtopics": [
                "Windows and Linux basics",
                "File and folder management",
                "Installing and uninstalling software",
                "System settings and maintenance",
                "Mobile operating systems",
            ]},
            {"name": "Word Processing", "subtopics": [
                "Creating and formatting documents",
                "Tables, images and graphics",
                "Mail merge",
                "Page layout and printing",
                "Document styles and templates",
            ]},
            {"name": "Spreadsheets and Databases", "subtopics": [
                "Spreadsheet basics and formulas",
                "Charts and graphs",
                "Data management and sorting",
                "Database concepts",
                "Creating simple databases",
            ]},
            {"name": "Internet and Communication", "subtopics": [
                "Internet concepts and browsers",
                "Email and communication tools",
                "Online safety and security",
                "Social media basics",
                "Internet for business",
            ]},
            {"name": "ICT Support and Maintenance", "subtopics": [
                "Computer assembly and disassembly",
                "Installing operating systems",
                "Troubleshooting common problems",
                "Computer security and antivirus",
                "Data backup and recovery",
            ]},
        ]
    },
    "Computer Applications": {
        "code": "T17",
        "topics": [
            {"name": "Computer Basics", "subtopics": [
                "Computer parts and functions",
                "Starting and shutting down a computer",
                "Keyboard and mouse skills",
                "Desktop and taskbar",
                "File management",
            ]},
            {"name": "Microsoft Word Basics", "subtopics": [
                "Typing and editing text",
                "Formatting text and paragraphs",
                "Inserting pictures and tables",
                "Spelling and grammar check",
                "Printing documents",
            ]},
            {"name": "Microsoft Excel Basics", "subtopics": [
                "Entering and editing data",
                "Basic formulas and functions",
                "Formatting cells",
                "Creating charts",
                "Sorting and filtering data",
            ]},
            {"name": "Microsoft PowerPoint", "subtopics": [
                "Creating presentations",
                "Slides and layouts",
                "Adding animations and transitions",
                "Inserting media",
                "Delivering presentations",
            ]},
            {"name": "Internet and Email", "subtopics": [
                "Browsing the internet",
                "Creating and using email accounts",
                "Attachments and downloads",
                "Online forms and applications",
                "Internet safety",
            ]},
            {"name": "Office Applications Practice", "subtopics": [
                "Preparing official letters",
                "Preparing reports",
                "Preparing budgets and spreadsheets",
                "Preparing presentations",
                "Combined office tasks (practical exam)",
            ]},
        ]
    },
    "Secretarial and Office Management": {
        "code": "T18",
        "topics": [
            {"name": "Introduction to Secretarial Work", "subtopics": [
                "Role of the secretary",
                "Office organisation and layout",
                "Office equipment",
                "Professional ethics and conduct",
                "Duties and responsibilities of a secretary",
            ]},
            {"name": "Office Communication", "subtopics": [
                "Written communication (letters, memos, reports)",
                "Electronic communication",
                "Telephone and reception skills",
                "Minutes and meeting procedures",
                "Handling official correspondence",
            ]},
            {"name": "Records and Filing Management", "subtopics": [
                "Filing systems and methods",
                "Indexing and classification",
                "Records retention and disposal",
                "Computerised records",
                "Confidentiality of records",
            ]},
            {"name": "Office Practice", "subtopics": [
                "Planning and organising work",
                "Managing appointments and diaries",
                "Travel arrangements",
                "Office supplies and requisitions",
                "Petty cash management",
            ]},
            {"name": "Typing and Word Processing", "subtopics": [
                "Keyboard mastery and speed",
                "Typing business documents",
                "Formatting official documents",
                "Typing tables and reports",
                "Audio transcription basics",
            ]},
            {"name": "Business Communication Skills", "subtopics": [
                "Business letters and their layout",
                "Report writing",
                "Preparing CVs and job applications",
                "Customer service skills",
                "Public relations",
            ]},
        ]
    },
    "Accounting and Bookkeeping": {
        "code": "T19",
        "topics": [
            {"name": "Introduction to Accounting", "subtopics": [
                "Meaning and importance of accounting",
                "Accounting concepts and principles",
                "The accounting equation",
                "Types of business organisations",
                "Accounting careers",
            ]},
            {"name": "Books of Accounts", "subtopics": [
                "Source documents",
                "Journals and ledgers",
                "Cash book and petty cash book",
                "Posting and balancing accounts",
                "The trial balance",
            ]},
            {"name": "Financial Statements", "subtopics": [
                "Income statement (profit and loss)",
                "Statement of financial position (balance sheet)",
                "Adjustments (accruals, prepayments, depreciation)",
                "Final accounts of sole traders",
                "Analysing financial statements",
            ]},
            {"name": "Banking and Cash Management", "subtopics": [
                "Bank accounts and bank reconciliation",
                "Cash handling and control",
                "Electronic banking (mobile money, EFD)",
                "Managing debtors and creditors",
                "Working capital management",
            ]},
            {"name": "Taxation and Compliance", "subtopics": [
                "Types of taxes in Tanzania",
                "TRA registration and obligations",
                "Value Added Tax (VAT) basics",
                "Income tax basics",
                "Payroll and PAYE",
            ]},
            {"name": "Bookkeeping Practice", "subtopics": [
                "Recording business transactions",
                "Preparing books for a small business",
                "Computerised bookkeeping (QuickBooks/Excel)",
                "Budgeting and control",
                "Financial record keeping for projects",
            ]},
        ]
    },
    "Entrepreneurship and Business Studies": {
        "code": "T20",
        "topics": [
            {"name": "Introduction to Entrepreneurship", "subtopics": [
                "Meaning of entrepreneurship",
                "Characteristics of entrepreneurs",
                "Role of entrepreneurs in the economy",
                "Business opportunities in Tanzania",
                "Entrepreneurial mindset",
            ]},
            {"name": "Business Planning", "subtopics": [
                "Idea generation and evaluation",
                "Market research",
                "Writing a business plan",
                "Business budgets",
                "Sources of business ideas",
            ]},
            {"name": "Marketing", "subtopics": [
                "Marketing concepts",
                "Market segmentation and targeting",
                "The marketing mix (4 Ps)",
                "Pricing strategies",
                "Promotion and advertising",
            ]},
            {"name": "Business Finance", "subtopics": [
                "Sources of finance",
                "Capital and working capital",
                "Simple financial records",
                "Break-even analysis",
                "Accessing loans and grants (SIDO, TASAF, banks)",
            ]},
            {"name": "Business Law and Ethics", "subtopics": [
                "Business registration (BRELA)",
                "Contracts and agreements",
                "Consumer protection",
                "Business ethics and social responsibility",
                "Employment and labour basics",
            ]},
            {"name": "Managing a Small Business", "subtopics": [
                "Operations management",
                "Customer relations",
                "Record keeping and stock control",
                "Growing the business",
                "Small business project (practical)",
            ]},
        ]
    },
    "Building and Civil Engineering": {
        "code": "T21",
        "topics": [
            {"name": "Introduction to Building and Civil Engineering", "subtopics": [
                "Meaning and scope of civil engineering",
                "Building construction process",
                "Roles of building professionals",
                "Construction drawings and symbols",
                "Site organisation and safety",
            ]},
            {"name": "Construction Materials", "subtopics": [
                "Soils and site investigation",
                "Cement, aggregates and water",
                "Timber and steel",
                "Concrete and mortar",
                "Material testing basics",
            ]},
            {"name": "Setting Out and Foundations", "subtopics": [
                "Setting out a building",
                "Levelling instruments and techniques",
                "Types of foundations",
                "Excavation and trenching",
                "Foundation construction",
            ]},
            {"name": "Superstructure Works", "subtopics": [
                "Walls and partitions",
                "Columns, beams and slabs",
                "Staircases and ramps",
                "Roofing structures",
                "Doors, windows and finishes",
            ]},
            {"name": "Roads and Infrastructure", "subtopics": [
                "Road construction basics",
                "Drainage structures (culverts, ditches)",
                "Water supply and sewerage works",
                "Bridges and culverts basics",
                "Maintenance of infrastructure",
            ]},
            {"name": "Quantity Surveying Basics", "subtopics": [
                "Taking off quantities",
                "Estimating and costing",
                "Contracts and tendering",
                "Project planning and scheduling",
                "Site supervision and inspection",
            ]},
        ]
    },
    "Mechanical Engineering": {
        "code": "T22",
        "topics": [
            {"name": "Introduction to Mechanical Engineering", "subtopics": [
                "Meaning and scope of mechanical engineering",
                "Workshop safety",
                "Mechanical drawing basics",
                "Measuring instruments (callipers, micrometres)",
                "Engineering materials and their properties",
            ]},
            {"name": "Hand and Machine Tools", "subtopics": [
                "Hand tools for fitting",
                "Bench work and fitting",
                "Drilling machines",
                "Lathe machine operations",
                "Grinding and cutting machines",
            ]},
            {"name": "Machine Elements", "subtopics": [
                "Screws, bolts and fasteners",
                "Bearings and lubrication",
                "Gears and gear trains",
                "Belts, pulleys and chains",
                "Shafts, keys and couplings",
            ]},
            {"name": "Mechanical Drives and Systems", "subtopics": [
                "Power transmission systems",
                "Pumps and compressors",
                "Hydraulic systems basics",
                "Pneumatic systems basics",
                "Maintenance of mechanical systems",
            ]},
            {"name": "Fitting and Fabrication", "subtopics": [
                "Marking out and precision fitting",
                "Filing, scraping and lapping",
                "Assembly and dismantling",
                "Fabrication of simple machines",
                "Testing and commissioning",
            ]},
            {"name": "Mechanical Maintenance", "subtopics": [
                "Preventive maintenance planning",
                "Fault diagnosis",
                "Repair of machine parts",
                "Welding in maintenance",
                "Maintenance records and reports",
            ]},
        ]
    },
    "Renewable Energy and Solar Installation": {
        "code": "T23",
        "topics": [
            {"name": "Introduction to Renewable Energy", "subtopics": [
                "Meaning and importance of renewable energy",
                "Types of renewable energy (solar, wind, hydro, biomass)",
                "Energy situation in Tanzania",
                "Climate change and energy",
                "Renewable energy policies",
            ]},
            {"name": "Solar Energy Principles", "subtopics": [
                "Solar radiation and insolation",
                "Photovoltaic effect",
                "Solar panel types and ratings",
                "Solar radiation measurement",
                "Siting of solar panels",
            ]},
            {"name": "Solar PV System Components", "subtopics": [
                "Solar panels and mounting",
                "Charge controllers",
                "Batteries (lead-acid, lithium)",
                "Inverters",
                "Cables, fuses and protection",
            ]},
            {"name": "Solar System Design and Sizing", "subtopics": [
                "Load assessment",
                "Sizing panels, batteries and inverters",
                "System wiring diagrams",
                "Cost estimation",
                "System layout and installation planning",
            ]},
            {"name": "Solar Installation and Maintenance", "subtopics": [
                "Installing panels and mounting structures",
                "Wiring and connecting components",
                "Testing and commissioning",
                "Troubleshooting faults",
                "Preventive maintenance",
            ]},
            {"name": "Other Renewable Technologies", "subtopics": [
                "Solar water heating",
                "Biogas production and use",
                "Wind energy basics",
                "Micro-hydro power",
                "Improved cook stoves and biomass briquettes",
            ]},
        ]
    },
    "Refrigeration and Air Conditioning": {
        "code": "T24",
        "topics": [
            {"name": "Introduction to Refrigeration", "subtopics": [
                "Meaning and importance of refrigeration",
                "Refrigeration applications (domestic, commercial, industrial)",
                "Refrigerants: types and properties",
                "Refrigeration tools and equipment",
                "Safety in refrigeration work",
            ]},
            {"name": "Refrigeration Cycle", "subtopics": [
                "The vapour compression cycle",
                "Components of a refrigeration system",
                "Compressors, condensers and evaporators",
                "Expansion devices",
                "Pressure and temperature in the cycle",
            ]},
            {"name": "System Components and Controls", "subtopics": [
                "Thermostats and pressure controls",
                "Solenoid valves and filter driers",
                "Fan and defrost controls",
                "Electrical circuits of refrigerators",
                "Capillary tubes and TXV",
            ]},
            {"name": "Installation and Commissioning", "subtopics": [
                "Installing domestic refrigerators",
                "Installing split air conditioners",
                "Evacuation and charging",
                "Leak testing",
                "Commissioning and performance testing",
            ]},
            {"name": "Maintenance and Fault Diagnosis", "subtopics": [
                "Routine maintenance of units",
                "Common faults and their symptoms",
                "Electrical fault finding",
                "Mechanical fault finding",
                "Repair and replacement of parts",
            ]},
            {"name": "Cold Storage and Commercial Systems", "subtopics": [
                "Walk-in cold rooms",
                "Freezers and display cabinets",
                "Air conditioning systems for buildings",
                "Heat load calculation basics",
                "Energy efficiency in refrigeration",
            ]},
        ]
    },
    "Graphic Design and Printing": {
        "code": "T25",
        "topics": [
            {"name": "Introduction to Graphic Design", "subtopics": [
                "Meaning and importance of graphic design",
                "Elements of design (line, shape, colour, texture)",
                "Principles of design (balance, contrast, rhythm)",
                "Design software overview",
                "Careers in graphic design",
            ]},
            {"name": "Drawing and Illustration", "subtopics": [
                "Freehand drawing",
                "Perspective drawing",
                "Lettering and typography",
                "Illustration techniques",
                "Colour mixing and theory",
            ]},
            {"name": "Computer Graphics", "subtopics": [
                "CorelDraw basics",
                "Adobe Photoshop basics",
                "Adobe Illustrator basics",
                "Working with images and layers",
                "Digital colour and resolution",
            ]},
            {"name": "Design Projects", "subtopics": [
                "Designing logos and brand identity",
                "Designing posters and banners",
                "Designing business cards and letterheads",
                "Designing brochures and magazines",
                "Designing packaging",
            ]},
            {"name": "Printing Technology", "subtopics": [
                "Introduction to printing processes",
                "Offset printing",
                "Digital printing",
                "Screen printing",
                "Pre-press and print preparation",
            ]},
            {"name": "Print Finishing and Business", "subtopics": [
                "Paper types and sizes",
                "Cutting, folding and binding",
                "Lamination and finishing",
                "Estimating print jobs",
                "Running a graphic design business",
            ]},
        ]
    },
    "Leather and Shoe Making": {
        "code": "T26",
        "topics": [
            {"name": "Introduction to Leather Work", "subtopics": [
                "Importance of leather industry in Tanzania",
                "Types and sources of hides and skins",
                "Leather work tools and equipment",
                "Workshop safety",
                "Leather products overview",
            ]},
            {"name": "Leather Processing", "subtopics": [
                "Flaying and handling of hides and skins",
                "Curing and preservation",
                "Soaking, liming and unhairing",
                "Tanning processes",
                "Dyeing and finishing leather",
            ]},
            {"name": "Leather Craftsmanship", "subtopics": [
                "Measuring and cutting leather",
                "Stitching leather by hand and machine",
                "Edge finishing and polishing",
                "Making leather bags and belts",
                "Making leather wallets and cases",
            ]},
            {"name": "Shoe Making", "subtopics": [
                "Anatomy of a shoe",
                "Foot measurement and sizing",
                "Lasting and pattern making",
                "Cutting uppers and soles",
                "Assembling and finishing shoes",
            ]},
            {"name": "Shoe Repair", "subtopics": [
                "Types of shoe damage",
                "Sole replacement",
                "Heel repair",
                "Upper repair and conditioning",
                "Setting up a shoe repair business",
            ]},
            {"name": "Leather Business and Quality", "subtopics": [
                "Leather quality and grading",
                "Product costing and pricing",
                "Marketing leather products",
                "Export opportunities",
                "Leather enterprise project (practical)",
            ]},
        ]
    },
    "Painting and Decorating": {
        "code": "T27",
        "topics": [
            {"name": "Introduction to Painting", "subtopics": [
                "Meaning and importance of painting",
                "Painting tools and equipment",
                "Types of paints and their uses",
                "Paint selection",
                "Workshop and site safety",
            ]},
            {"name": "Surface Preparation", "subtopics": [
                "Preparing new surfaces",
                "Preparing old surfaces",
                "Filling holes and cracks",
                "Sanding and smoothing",
                "Priming and undercoating",
            ]},
            {"name": "Painting Techniques", "subtopics": [
                "Brush painting techniques",
                "Roller painting",
                "Spray painting",
                "Painting woodwork",
                "Painting metal surfaces",
            ]},
            {"name": "Decorative Finishes", "subtopics": [
                "Colour mixing and matching",
                "Stencilling and wall art",
                "Textured finishes",
                "Varnishing and polishing",
                "Wallpaper hanging",
            ]},
            {"name": "Sign Writing and Lettering", "subtopics": [
                "Lettering styles",
                "Designing signs",
                "Painting signs and lettering",
                "Applying graphics",
                "Protective coatings for signs",
            ]},
            {"name": "Estimating and Project Work", "subtopics": [
                "Measuring areas for painting",
                "Estimating paint and materials",
                "Costing painting jobs",
                "Painting a complete room (project)",
                "Quality control and inspection",
            ]},
        ]
    },
    "Woodwork and Furniture Making": {
        "code": "T28",
        "topics": [
            {"name": "Introduction to Woodwork", "subtopics": [
                "Meaning and importance of woodwork",
                "Wood as a material",
                "Woodwork tools and machines",
                "Workshop safety",
                "Reading woodwork drawings",
            ]},
            {"name": "Timber and Manufactured Boards", "subtopics": [
                "Hardwoods and softwoods",
                "Timber defects",
                "Seasoning and preservation",
                "Plywood, MDF and particle board",
                "Timber selection for projects",
            ]},
            {"name": "Woodworking Machines", "subtopics": [
                "Circular saw",
                "Planer and thicknesser",
                "Band saw",
                "Router and spindle moulder",
                "Machine safety and maintenance",
            ]},
            {"name": "Furniture Construction", "subtopics": [
                "Tables and desks",
                "Chairs and stools",
                "Cabinets and wardrobes",
                "Beds and headboards",
                "Joints and fittings for furniture",
            ]},
            {"name": "Upholstery", "subtopics": [
                "Upholstery materials",
                "Cutting and sewing covers",
                "Springing and stuffing",
                "Re-upholstering chairs",
                "Cushion making",
            ]},
            {"name": "Finishing and Business", "subtopics": [
                "Sanding and preparation",
                "Staining and varnishing",
                "Lacquering and polishing",
                "Estimating furniture costs",
                "Furniture making project (practical)",
            ]},
        ]
    },
    "Food Processing and Preservation": {
        "code": "T29",
        "topics": [
            {"name": "Introduction to Food Processing", "subtopics": [
                "Meaning and importance of food processing",
                "Food processing in Tanzania",
                "Food processing equipment",
                "Food safety and standards (TBS)",
                "Careers in food processing",
            ]},
            {"name": "Cereal and Grain Processing", "subtopics": [
                "Maize and rice milling",
                "Flour production",
                "Making breakfast cereals",
                "Grain storage and handling",
                "Quality control of milled products",
            ]},
            {"name": "Fruit and Vegetable Processing", "subtopics": [
                "Juice extraction and processing",
                "Drying of fruits and vegetables",
                "Jams, jellies and preserves",
                "Pickling",
                "Packaging of processed produce",
            ]},
            {"name": "Food Preservation Methods", "subtopics": [
                "Drying and dehydration",
                "Canning and bottling",
                "Freezing",
                "Fermentation (yoghurt, sour milk)",
                "Use of preservatives",
            ]},
            {"name": "Dairy and Meat Processing", "subtopics": [
                "Milk processing and pasteurisation",
                "Cheese and butter making",
                "Meat processing and curing",
                "Sausage making",
                "Fish processing and smoking",
            ]},
            {"name": "Processing Enterprise", "subtopics": [
                "Product development",
                "Costing and pricing products",
                "Packaging and labelling (TBS requirements)",
                "Marketing processed foods",
                "Food processing project (practical)",
            ]},
        ]
    },
    "Occupational Safety and Health": {
        "code": "T30",
        "topics": [
            {"name": "Introduction to Occupational Safety and Health", "subtopics": [
                "Meaning and importance of OSH",
                "OSH legislation in Tanzania (OSHA 2003)",
                "Roles of employers and employees",
                "OSH institutions (OSHC, NSSF)",
                "Costs of workplace accidents",
            ]},
            {"name": "Hazard Identification and Risk Assessment", "subtopics": [
                "Types of hazards (physical, chemical, biological, ergonomic)",
                "Hazard identification methods",
                "Risk assessment process",
                "Risk control hierarchy",
                "Workplace inspections",
            ]},
            {"name": "Workplace Safety", "subtopics": [
                "Machine guarding",
                "Electrical safety",
                "Fire safety and fire fighting",
                "Working at height",
                "Confined space safety",
            ]},
            {"name": "Chemical and Material Safety", "subtopics": [
                "Chemical hazards and labelling (GHS)",
                "Safety data sheets (SDS)",
                "Storage and handling of chemicals",
                "Personal protective equipment (PPE)",
                "Waste management",
            ]},
            {"name": "Occupational Health", "subtopics": [
                "Occupational diseases",
                "Ergonomics and manual handling",
                "Noise and vibration",
                "Workplace stress and wellness",
                "Medical surveillance",
            ]},
            {"name": "Emergency Preparedness and First Aid", "subtopics": [
                "Emergency plans and procedures",
                "First aid principles",
                "Treating common workplace injuries",
                "Incident reporting and investigation",
                "OSH committees and training",
            ]},
        ]
    },
    "Communication Skills": {
        "code": "T31",
        "topics": [
            {"name": "Introduction to Communication", "subtopics": [
                "Meaning and importance of communication",
                "Elements of the communication process",
                "Types of communication",
                "Barriers to communication",
                "Overcoming communication barriers",
            ]},
            {"name": "Oral Communication", "subtopics": [
                "Speaking clearly and confidently",
                "Listening skills",
                "Questioning techniques",
                "Presentations and public speaking",
                "Group discussions and meetings",
            ]},
            {"name": "Written Communication", "subtopics": [
                "Writing effective sentences and paragraphs",
                "Business letters and emails",
                "Reports and proposals",
                "Minutes and memos",
                "Editing and proofreading",
            ]},
            {"name": "Non-verbal Communication", "subtopics": [
                "Body language and posture",
                "Facial expressions and eye contact",
                "Gestures and personal space",
                "Dress and appearance",
                "Cultural aspects of non-verbal communication",
            ]},
            {"name": "Workplace Communication", "subtopics": [
                "Customer service communication",
                "Telephone and reception etiquette",
                "Dealing with difficult people",
                "Team communication and cooperation",
                "Conflict resolution",
            ]},
            {"name": "Communication Technology", "subtopics": [
                "Email and instant messaging",
                "Video conferencing",
                "Social media in business",
                "Report presentation tools",
                "Professional online communication",
            ]},
        ]
    },
    "Applied Mathematics for Trades": {
        "code": "T32",
        "topics": [
            {"name": "Basic Arithmetic for Trades", "subtopics": [
                "Whole numbers and operations",
                "Fractions, decimals and percentages",
                "Ratios and proportions",
                "Averages",
                "Rounding and estimation",
            ]},
            {"name": "Measurement", "subtopics": [
                "Units of length, mass, capacity, time",
                "Area and perimeter",
                "Volume and capacity of solids",
                "Angles and their measurement",
                "Metric conversion",
            ]},
            {"name": "Algebra for Trades", "subtopics": [
                "Algebraic expressions",
                "Simple equations",
                "Formulas and substitution",
                "Transposing formulas",
                "Word problems in trades",
            ]},
            {"name": "Geometry for Trades", "subtopics": [
                "Lines, angles and shapes",
                "Triangles and the theorem of Pythagoras",
                "Circles and circumference",
                "Areas of common shapes",
                "Volumes of prisms and cylinders",
            ]},
            {"name": "Graphs and Data", "subtopics": [
                "Reading and drawing graphs",
                "Bar charts and pie charts",
                "Tables of data",
                "Interpreting statistical data",
                "Charts for business and projects",
            ]},
            {"name": "Practical Applications", "subtopics": [
                "Costing and pricing materials",
                "Work, time and rates",
                "Scales and scale drawings",
                "Electricity and energy calculations",
                "Measurements for construction and trades",
            ]},
        ]
    },
    "Basic Health and Caregiving": {
        "code": "T33",
        "topics": [
            {"name": "Introduction to Caregiving", "subtopics": [
                "Meaning and role of a caregiver",
                "Caregiving settings (home, hospital, community)",
                "Qualities of a good caregiver",
                "Ethics and confidentiality",
                "Caregiving careers",
            ]},
            {"name": "Basic Human Anatomy and Hygiene", "subtopics": [
                "Body systems overview",
                "Personal hygiene",
                "Environmental hygiene",
                "Hand washing and infection control",
                "Safe disposal of waste",
            ]},
            {"name": "Patient Care", "subtopics": [
                "Bathing and grooming patients",
                "Feeding and nutrition for patients",
                "Mobility, lifting and positioning",
                "Pressure sore prevention",
                "Bed making and linen care",
            ]},
            {"name": "Vital Signs and Observation", "subtopics": [
                "Temperature, pulse, respiration",
                "Blood pressure measurement",
                "Recording and reporting observations",
                "Monitoring intake and output",
                "Recognising warning signs",
            ]},
            {"name": "First Aid and Emergencies", "subtopics": [
                "Principles of first aid",
                "Wounds, bleeding and dressings",
                "Fractures and sprains",
                "Choking and resuscitation (CPR)",
                "Emergency referral procedures",
            ]},
            {"name": "Care for Special Groups", "subtopics": [
                "Care of the elderly",
                "Care of children",
                "Care of people with disabilities",
                "Care of chronic illness patients",
                "Mental health support basics",
            ]},
        ]
    },
    "Automotive Electrical Systems": {
        "code": "T34",
        "topics": [
            {"name": "Introduction to Automotive Electric", "subtopics": [
                "Importance of vehicle electrical systems",
                "Electrical principles for vehicles",
                "Vehicle wiring and colour codes",
                "Automotive electrical tools",
                "Safety with vehicle electrical systems",
            ]},
            {"name": "Batteries and Charging Systems", "subtopics": [
                "Battery types and construction",
                "Battery testing and maintenance",
                "Alternators and regulators",
                "Charging circuit testing",
                "Battery safety and disposal",
            ]},
            {"name": "Starting Systems", "subtopics": [
                "Starter motor construction",
                "Starter circuit and solenoid",
                "Starting system testing",
                "Starter faults and repair",
                "Preventive maintenance",
            ]},
            {"name": "Lighting and Accessories", "subtopics": [
                "Lighting circuits",
                "Headlamps, indicators and brake lights",
                "Horns, wipers and gauges",
                "Fuses, relays and switches",
                "Wiring accessories",
            ]},
            {"name": "Electronic Systems", "subtopics": [
                "Sensors and actuators",
                "Engine control unit (ECU) basics",
                "Diagnostic tools (OBD scanners)",
                "Reading diagnostic codes",
                "Common electronic faults",
            ]},
            {"name": "Diagnosis and Repair", "subtopics": [
                "Wiring diagrams and circuits",
                "Fault finding procedures",
                "Repairing wiring and connections",
                "Installation of accessories (alarms, audio)",
                "Final testing and inspection",
            ]},
        ]
    },
    "Water Supply and Sanitation": {
        "code": "T35",
        "topics": [
            {"name": "Introduction to Water and Sanitation", "subtopics": [
                "Importance of water supply and sanitation",
                "Water sources in Tanzania",
                "Water quality and standards",
                "Sanitation and public health",
                "Water and sanitation careers",
            ]},
            {"name": "Water Treatment", "subtopics": [
                "Water treatment processes",
                "Sedimentation and filtration",
                "Disinfection (chlorination)",
                "Water quality testing",
                "Small-scale treatment systems",
            ]},
            {"name": "Water Distribution Systems", "subtopics": [
                "Pipe networks and layouts",
                "Gravity and pumped systems",
                "Valves, hydrants and fittings",
                "Tanks and reservoirs",
                "Laying and testing pipelines",
            ]},
            {"name": "Rural Water Supply", "subtopics": [
                "Boreholes and wells",
                "Hand pumps and installation",
                "Rainwater harvesting",
                "Community water projects",
                "Operation and maintenance of rural systems",
            ]},
            {"name": "Sanitation Facilities", "subtopics": [
                "Latrines: types and construction",
                "Ventilated improved pit latrines",
                "Septic tanks and soakaways",
                "Wastewater treatment basics",
                "Hygiene promotion in communities",
            ]},
            {"name": "Project Management in Water", "subtopics": [
                "Community mobilisation",
                "Water project planning",
                "Costing water projects",
                "Monitoring and evaluation",
                "Water governance and regulations",
            ]},
        ]
    },
    "Baking and Confectionery": {
        "code": "T36",
        "topics": [
            {"name": "Introduction to Baking", "subtopics": [
                "Meaning and importance of baking",
                "Bakery equipment and utensils",
                "Bakery ingredients",
                "Bakery hygiene and safety",
                "Careers in baking",
            ]},
            {"name": "Bread Making", "subtopics": [
                "Ingredients and their functions",
                "Mixing and kneading",
                "Fermentation and proofing",
                "Shaping bread",
                "Baking and cooling bread",
            ]},
            {"name": "Cakes and Sponges", "subtopics": [
                "Cake making methods",
                "Sponge and Genoese cakes",
                "Fruit cakes",
                "Cupcakes and muffins",
                "Cake faults and remedies",
            ]},
            {"name": "Pastry and Pies", "subtopics": [
                "Shortcrust pastry",
                "Flaky and puff pastry",
                "Choux pastry",
                "Pies, tarts and quiches",
                "Samosa and maandazi (Swahili snacks)",
            ]},
            {"name": "Confectionery", "subtopics": [
                "Sugar syrups and sweets",
                "Chocolates and coatings",
                "Biscuits and cookies",
                "Creams, fillings and icings",
                "Cake decoration basics",
            ]},
            {"name": "Bakery Business", "subtopics": [
                "Menu and product costing",
                "Bakery layout and equipment",
                "Stock control",
                "Marketing bakery products",
                "Bakery project (practical)",
            ]},
        ]
    },
}


def seed_technical_topics(apps, schema_editor):
    Subject = apps.get_model('field_app', 'Subject')
    SubjectTopic = apps.get_model('curriculum', 'SubjectTopic')
    TopicSubtopic = apps.get_model('curriculum', 'TopicSubtopic')
    db = schema_editor.connection.alias

    total_topics = 0
    total_subtopics = 0
    for subject_name, subject_data in TECHNICAL_SYLLABUS.items():
        subj = Subject.objects.using(db).filter(code=subject_data['code']).first()
        if not subj:
            subj = Subject.objects.using(db).filter(name=subject_name).first()
        if not subj:
            continue

        # Existing topic names for this subject (all classes) to avoid duplicates
        existing_topic_keys = set(
            SubjectTopic.objects.using(db).filter(subject=subj)
            .values_list('class_name', 'name')
        )

        # ── 1) Create all new topics in bulk ──
        new_topics = []
        for class_name in TECHNICAL_CLASSES:
            for topic_data in subject_data['topics']:
                if (class_name, topic_data['name']) in existing_topic_keys:
                    continue
                new_topics.append(SubjectTopic(
                    subject=subj,
                    class_name=class_name,
                    name=topic_data['name'],
                    order=topic_data.get('order', 0),
                ))
        SubjectTopic.objects.using(db).bulk_create(new_topics, ignore_conflicts=True)
        total_topics += len(new_topics)

        # ── 2) Create subtopics in bulk (only for topics we know exist) ──
        topic_ids = list(
            SubjectTopic.objects.using(db).filter(
                subject=subj, class_name__in=TECHNICAL_CLASSES
            ).values_list('id', flat=True)
        )
        topic_id_by_name = {}
        if topic_ids:
            for t in SubjectTopic.objects.using(db).filter(id__in=topic_ids):
                topic_id_by_name[(t.class_name, t.name)] = t.id

        existing_sub_keys = set()
        if topic_ids:
            existing_sub_keys = set(
                TopicSubtopic.objects.using(db).filter(topic_id__in=topic_ids)
                .values_list('topic_id', 'name')
            )

        new_subtopics = []
        for class_name in TECHNICAL_CLASSES:
            for topic_data in subject_data['topics']:
                tid = topic_id_by_name.get((class_name, topic_data['name']))
                if not tid:
                    continue
                for sub_order, subtopic_name in enumerate(topic_data['subtopics'], 1):
                    if (tid, subtopic_name) in existing_sub_keys:
                        continue
                    new_subtopics.append(TopicSubtopic(
                        topic_id=tid, name=subtopic_name, order=sub_order,
                    ))
        TopicSubtopic.objects.using(db).bulk_create(new_subtopics, ignore_conflicts=True)
        total_subtopics += len(new_subtopics)

    print(f"[Technical Syllabus] {len(TECHNICAL_SYLLABUS)} subjects | "
          f"{total_topics} topics | {total_subtopics} subtopics")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0008_alter_tlmteacher_theme_generatedexam_tlmlogbookentry'),
        ('field_app', '0034_technical_veta_schools_subjects'),
    ]

    operations = [
        migrations.RunPython(seed_technical_topics, noop),
    ]
