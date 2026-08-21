"""
100개 신용장(L/C) JSON 데이터 생성 스크립트
LC-2022-011 ~ LC-2022-110
"""
import json
import os
import random

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "lc_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 기초 데이터 풀 ────────────────────────────────────────────────────────────

APPLICANTS = [
    "SUNRISE INDUSTRIAL GROUP CO., LTD.",
    "AMERICAN MEDICAL SUPPLIES INC.",
    "SOUTHERN LOGISTICS PTY LTD",
    "TOKYO TRADING CORP.",
    "SHANGHAI IMPORT & EXPORT CO., LTD.",
    "EUROPEAN TECH SOLUTIONS GMBH",
    "GULF TRADING ENTERPRISES LLC",
    "PACIFIC RIM COMMODITIES INC.",
    "NORTHERN EUROPE TRADE AS",
    "BRAZIL AGRO EXPORTS LTDA",
    "INDIA TEXTILE MILLS PVT. LTD.",
    "CANADIAN RESOURCE GROUP INC.",
    "MEXICO MANUFACTURING SA DE CV",
    "SOUTH AFRICA METALS (PTY) LTD.",
    "VIETNAM GARMENT INDUSTRY CO., LTD.",
    "PHILIPPINES CONSUMER GOODS INC.",
    "INDONESIA PALM OIL CORP.",
    "MALAYSIA PETROCHEMICALS BHD.",
    "THAILAND RUBBER EXPORTS CO., LTD.",
    "EGYPT COTTON TRADING LLC",
    "TURKEY MACHINERY HOLDINGS A.S.",
    "ARGENTINA SOYA EXPORTS SRL",
    "CHILE COPPER MINING LTD.",
    "COLOMBIA COFFEE TRADERS SAS",
    "POLAND AUTOMOTIVE PARTS SP ZOO",
    "CZECH GLASS WORKS AS",
    "HUNGARY PHARMACEUTICAL KFT.",
    "ROMANIA STEEL MANUFACTURING SRL",
    "UKRAINE GRAIN EXPORTS LLC",
    "KAZAKHSTAN OIL & GAS JSC",
]

BENEFICIARIES = [
    "KOREA MACHINERY EXPORTS INC.",
    "KOREA BIOMEDICAL EXPORTS LTD.",
    "KOREA CABLE TECH CO., LTD.",
    "SAMSUNG SEMICONDUCTOR KOREA INC.",
    "HYUNDAI STEEL PRODUCTS CO., LTD.",
    "LG CHEMICAL TRADING INC.",
    "DAEWOO ELECTRONICS EXPORT CO., LTD.",
    "SK ENERGY TRADING CORP.",
    "POSCO INTERNATIONAL CORP.",
    "HANWHA DEFENSE SYSTEMS LTD.",
    "DOOSAN HEAVY INDUSTRIES EXPORT CO.",
    "LOTTE CHEMICAL CO., LTD.",
    "CJ LOGISTICS INTERNATIONAL INC.",
    "KIAMOTOR PARTS EXPORT CO., LTD.",
    "KOREA SHIPBUILDING EXPORT LTD.",
    "KOREA FOOD INDUSTRIES CO., LTD.",
    "KOREA PHARMA EXPORTS INC.",
    "INCHEON ELECTRONICS TRADE CO., LTD.",
    "BUSAN PORT LOGISTICS INC.",
    "KOREA TEXTILE EXPORTS CO., LTD.",
    "GWANGYANG STEEL EXPORTS CO., LTD.",
    "ULSAN PETROCHEMICAL TRADE LTD.",
    "SUWON SEMICONDUCTOR EXPORT INC.",
    "CHANGWON MACHINERY EXPORTS CO., LTD.",
    "ANSAN PRECISION PARTS CO., LTD.",
    "DAEJEON OPTICAL EXPORTS INC.",
    "POHANG IRON & STEEL EXPORT LTD.",
    "GIMHAE AEROSPACE PARTS CO., LTD.",
    "IKSAN AGRO EXPORTS CO., LTD.",
    "YEOSU CHEMICAL EXPORTS INC.",
]

ISSUING_BANKS = [
    "WOORI BANK, SEOUL",
    "BANK OF AMERICA, N.A.",
    "COMMONWEALTH BANK OF AUSTRALIA",
    "NATIONAL AUSTRALIA BANK",
    "BANK OF CHINA, BEIJING",
    "HSBC BANK PLC, LONDON",
    "DEUTSCHE BANK AG, FRANKFURT",
    "BNP PARIBAS, PARIS",
    "SOCIETE GENERALE, PARIS",
    "CREDIT SUISSE AG, ZURICH",
    "UBS AG, ZURICH",
    "ING BANK N.V., AMSTERDAM",
    "ABN AMRO BANK N.V., AMSTERDAM",
    "RABOBANK, UTRECHT",
    "STANDARD CHARTERED BANK, SINGAPORE",
    "DBS BANK LTD., SINGAPORE",
    "MITSUBISHI UFJ FINANCIAL GROUP, TOKYO",
    "SUMITOMO MITSUI BANKING CORP., TOKYO",
    "MIZUHO BANK LTD., TOKYO",
    "INDUSTRIAL AND COMMERCIAL BANK OF CHINA",
    "CHINA CONSTRUCTION BANK, BEIJING",
    "AGRICULTURAL BANK OF CHINA",
    "BANK OF COMMUNICATIONS, SHANGHAI",
    "EMIRATES NBD, DUBAI",
    "ABU DHABI COMMERCIAL BANK, ABU DHABI",
    "QATAR NATIONAL BANK, DOHA",
    "STATE BANK OF INDIA, MUMBAI",
    "HDFC BANK LTD., MUMBAI",
    "ICICI BANK LTD., MUMBAI",
    "FIRST NATIONAL BANK, JOHANNESBURG",
]

ADVISING_BANKS = [
    "CITIBANK N.A., NEW YORK",
    "SHINHAN BANK, SEOUL",
    "HANA BANK, INCHEON",
    "KEB HANA BANK, SEOUL",
    "KB KOOKMIN BANK, SEOUL",
    "IBK INDUSTRIAL BANK OF KOREA",
    "NH NONGHYUP BANK, SEOUL",
    "STANDARD CHARTERED BANK KOREA LTD.",
    "JP MORGAN CHASE BANK, N.A., NEW YORK",
    "WELLS FARGO BANK, N.A., SAN FRANCISCO",
    "BARCLAYS BANK PLC, LONDON",
    "LLOYDS BANKING GROUP PLC, LONDON",
    "NATWEST BANK, EDINBURGH",
    "ROYAL BANK OF CANADA, TORONTO",
    "TORONTO-DOMINION BANK, TORONTO",
    "BANK OF NOVA SCOTIA, TORONTO",
    "ANZ BANKING GROUP, MELBOURNE",
    "WESTPAC BANKING CORP., SYDNEY",
    "COMMERZBANK AG, FRANKFURT",
    "UNICREDIT SPA, MILAN",
    "INTESA SANPAOLO SPA, MILAN",
    "SANTANDER SA, MADRID",
    "BBVA SA, MADRID",
    "NORDEA BANK AB, STOCKHOLM",
    "SKANDINAVISKA ENSKILDA BANKEN, STOCKHOLM",
    "DNB BANK ASA, OSLO",
    "DANSKE BANK A/S, COPENHAGEN",
    "PKO BANK POLSKI SA, WARSAW",
    "ERSTE BANK AG, VIENNA",
    "BANK MANDIRI, JAKARTA",
]

PORTS = [
    # Asia
    "BUSAN, KOREA", "INCHEON, KOREA", "PYEONGTAEK, KOREA",
    "SHANGHAI, CHINA", "NINGBO, CHINA", "GUANGZHOU, CHINA", "SHENZHEN, CHINA",
    "TIANJIN, CHINA", "QINGDAO, CHINA", "DALIAN, CHINA",
    "TOKYO, JAPAN", "OSAKA, JAPAN", "YOKOHAMA, JAPAN", "KOBE, JAPAN", "NAGOYA, JAPAN",
    "SINGAPORE, SINGAPORE",
    "HONG KONG, CHINA",
    "KAOHSIUNG, TAIWAN", "KEELUNG, TAIWAN",
    "PORT KLANG, MALAYSIA", "PENANG, MALAYSIA",
    "LAEM CHABANG, THAILAND", "BANGKOK, THAILAND",
    "HO CHI MINH CITY, VIETNAM", "HAI PHONG, VIETNAM",
    "JAKARTA, INDONESIA", "SURABAYA, INDONESIA",
    "MANILA, PHILIPPINES",
    "MUMBAI, INDIA", "CHENNAI, INDIA", "KOLKATA, INDIA",
    "COLOMBO, SRI LANKA",
    "CHITTAGONG, BANGLADESH",
    "KARACHI, PAKISTAN",
    # Europe
    "ROTTERDAM, NETHERLANDS",
    "HAMBURG, GERMANY", "BREMEN, GERMANY",
    "ANTWERP, BELGIUM",
    "FELIXSTOWE, UK", "SOUTHAMPTON, UK",
    "LE HAVRE, FRANCE", "MARSEILLE, FRANCE",
    "BARCELONA, SPAIN", "VALENCIA, SPAIN", "BILBAO, SPAIN",
    "GENOVA, ITALY", "NAPLES, ITALY", "TRIESTE, ITALY",
    "PIRAEUS, GREECE",
    "ISTANBUL, TURKEY", "IZMIR, TURKEY",
    "GDANSK, POLAND",
    "GDYNIA, POLAND",
    "HELSINKI, FINLAND",
    "GOTHENBURG, SWEDEN",
    "OSLO, NORWAY",
    "COPENHAGEN, DENMARK",
    # America
    "LOS ANGELES, USA", "LONG BEACH, USA", "NEW YORK, USA", "SEATTLE, USA",
    "HOUSTON, USA", "NEW ORLEANS, USA", "SAVANNAH, USA", "CHARLESTON, USA",
    "VANCOUVER, CANADA", "MONTREAL, CANADA",
    "MANZANILLO, MEXICO", "VERACRUZ, MEXICO",
    "SANTOS, BRAZIL", "RIO DE JANEIRO, BRAZIL",
    "BUENOS AIRES, ARGENTINA",
    "VALPARAISO, CHILE",
    "CALLAO, PERU",
    "CARTAGENA, COLOMBIA",
    # Middle East & Africa
    "JEDDAH, SAUDI ARABIA", "DAMMAM, SAUDI ARABIA",
    "DUBAI, UAE", "ABU DHABI, UAE",
    "SALALAH, OMAN",
    "PORT SAID, EGYPT",
    "DURBAN, SOUTH AFRICA",
    "MOMBASA, KENYA",
    "LAGOS, NIGERIA",
    "DAR ES SALAAM, TANZANIA",
    # Oceania
    "SYDNEY, AUSTRALIA", "MELBOURNE, AUSTRALIA", "BRISBANE, AUSTRALIA",
    "AUCKLAND, NEW ZEALAND",
]

EXPIRY_PLACES = [
    "SEOUL", "NEW YORK", "LONDON", "SINGAPORE", "HONG KONG", "TOKYO", "SYDNEY",
    "HAMBURG", "ROTTERDAM", "DUBAI", "SHANGHAI", "PARIS", "FRANKFURT", "ZURICH",
    "MUMBAI", "BUSAN", "AMSTERDAM", "BRUSSELS", "VIENNA", "MADRID",
]

GOODS_CATALOG = [
    # 기계/설비
    {"goods": "SAW MACHINE", "keywords": ["SAW", "MACHINE"], "weight": (500, 5000), "cbm": (200, 3000)},
    {"goods": "CNC MACHINING CENTER", "keywords": ["CNC", "MACHINING"], "weight": (2000, 15000), "cbm": (1000, 8000)},
    {"goods": "HYDRAULIC PRESS MACHINE", "keywords": ["HYDRAULIC", "PRESS"], "weight": (3000, 20000), "cbm": (1500, 10000)},
    {"goods": "INDUSTRIAL BOILER", "keywords": ["BOILER", "INDUSTRIAL"], "weight": (5000, 30000), "cbm": (2000, 15000)},
    {"goods": "ELECTRIC GENERATOR SET", "keywords": ["GENERATOR", "ELECTRIC"], "weight": (1000, 8000), "cbm": (500, 4000)},
    {"goods": "AIR COMPRESSOR", "keywords": ["COMPRESSOR", "AIR"], "weight": (800, 5000), "cbm": (400, 3000)},
    {"goods": "DIESEL ENGINE", "keywords": ["DIESEL", "ENGINE"], "weight": (2000, 12000), "cbm": (1000, 6000)},
    {"goods": "FORKLIFT TRUCK", "keywords": ["FORKLIFT", "TRUCK"], "weight": (3000, 10000), "cbm": (2000, 8000)},
    {"goods": "WELDING MACHINE", "keywords": ["WELDING", "MACHINE"], "weight": (200, 2000), "cbm": (100, 1000)},
    {"goods": "LATHE MACHINE", "keywords": ["LATHE", "MACHINE"], "weight": (1000, 8000), "cbm": (500, 4000)},
    # 전자/반도체
    {"goods": "SEMICONDUCTOR CHIPS, INTEGRATED CIRCUITS", "keywords": ["SEMICONDUCTOR", "INTEGRATED", "CIRCUIT"], "weight": (50, 500), "cbm": (10, 200)},
    {"goods": "LCD DISPLAY PANELS, FLAT SCREEN MODULES", "keywords": ["LCD", "DISPLAY", "PANEL"], "weight": (200, 2000), "cbm": (100, 1000)},
    {"goods": "PRINTED CIRCUIT BOARD", "keywords": ["CIRCUIT", "BOARD"], "weight": (100, 1000), "cbm": (50, 500)},
    {"goods": "POWER CONVERTER, PAINTS, PRINTING INKS", "keywords": ["POWER", "CONVERTER"], "weight": (500, 3000), "cbm": (200, 1500)},
    {"goods": "LED LIGHTING FIXTURES", "keywords": ["LED", "LIGHTING"], "weight": (200, 1500), "cbm": (100, 800)},
    {"goods": "SOLAR PANEL MODULES", "keywords": ["SOLAR", "PANEL"], "weight": (500, 5000), "cbm": (300, 3000)},
    {"goods": "LITHIUM ION BATTERY CELLS", "keywords": ["LITHIUM", "BATTERY"], "weight": (300, 3000), "cbm": (100, 1500)},
    {"goods": "ELECTRIC MOTOR, SERVO DRIVE", "keywords": ["ELECTRIC", "MOTOR", "SERVO"], "weight": (500, 5000), "cbm": (200, 2500)},
    # 의료
    {"goods": "MEDICAL SUTURES, SURGICAL COVERINGS, STERILE SUPPLIES", "keywords": ["MEDICAL", "SURGICAL", "STERILE"], "weight": (100, 1500), "cbm": (50, 1000)},
    {"goods": "DIAGNOSTIC ULTRASOUND EQUIPMENT", "keywords": ["DIAGNOSTIC", "ULTRASOUND"], "weight": (200, 2000), "cbm": (100, 1000)},
    {"goods": "SURGICAL GLOVES, DISPOSABLE MASKS, PROTECTIVE GOWN", "keywords": ["SURGICAL", "DISPOSABLE", "PROTECTIVE"], "weight": (200, 2000), "cbm": (100, 1000)},
    {"goods": "PHARMACEUTICAL TABLETS, CAPSULES, ANTIBIOTICS", "keywords": ["PHARMACEUTICAL", "ANTIBIOTIC"], "weight": (100, 1000), "cbm": (50, 500)},
    {"goods": "X-RAY MACHINE, RADIOLOGICAL EQUIPMENT", "keywords": ["X-RAY", "RADIOLOGICAL"], "weight": (500, 5000), "cbm": (200, 2500)},
    {"goods": "PATIENT MONITORING SYSTEM", "keywords": ["PATIENT", "MONITORING"], "weight": (100, 1000), "cbm": (50, 500)},
    # 화학/석유
    {"goods": "POLYETHYLENE RESIN, POLYPROPYLENE GRANULES", "keywords": ["POLYETHYLENE", "POLYPROPYLENE"], "weight": (5000, 50000), "cbm": (3000, 30000)},
    {"goods": "INDUSTRIAL LUBRICANT OIL", "keywords": ["LUBRICANT", "OIL", "INDUSTRIAL"], "weight": (2000, 20000), "cbm": (1500, 15000)},
    {"goods": "EPOXY RESIN, HARDENER", "keywords": ["EPOXY", "RESIN", "HARDENER"], "weight": (1000, 10000), "cbm": (500, 5000)},
    {"goods": "SODIUM HYDROXIDE, CAUSTIC SODA", "keywords": ["SODIUM", "HYDROXIDE", "CAUSTIC"], "weight": (3000, 30000), "cbm": (1500, 15000)},
    {"goods": "TITANIUM DIOXIDE PIGMENT", "keywords": ["TITANIUM", "DIOXIDE", "PIGMENT"], "weight": (2000, 20000), "cbm": (1000, 10000)},
    # 철강/금속
    {"goods": "HOT ROLLED STEEL COIL", "keywords": ["STEEL", "COIL", "HOT ROLLED"], "weight": (10000, 100000), "cbm": (3000, 30000)},
    {"goods": "COLD ROLLED STEEL SHEET", "keywords": ["STEEL", "SHEET", "COLD ROLLED"], "weight": (8000, 80000), "cbm": (2000, 25000)},
    {"goods": "STAINLESS STEEL PIPE, TUBE", "keywords": ["STAINLESS", "STEEL", "PIPE"], "weight": (3000, 30000), "cbm": (1500, 15000)},
    {"goods": "ALUMINUM ALLOY INGOT", "keywords": ["ALUMINUM", "ALLOY", "INGOT"], "weight": (5000, 50000), "cbm": (2000, 20000)},
    {"goods": "COPPER CATHODE", "keywords": ["COPPER", "CATHODE"], "weight": (5000, 50000), "cbm": (2000, 20000)},
    # 섬유/의류
    {"goods": "POLYESTER YARN, WOVEN FABRIC", "keywords": ["POLYESTER", "YARN", "FABRIC"], "weight": (1000, 10000), "cbm": (500, 5000)},
    {"goods": "COTTON FABRIC, GREY CLOTH", "keywords": ["COTTON", "FABRIC"], "weight": (1000, 10000), "cbm": (500, 5000)},
    {"goods": "KNITTED GARMENT, UNDERWEAR", "keywords": ["KNITTED", "GARMENT"], "weight": (500, 5000), "cbm": (300, 3000)},
    {"goods": "WOOLEN BLANKET, BED SHEETS", "keywords": ["WOOLEN", "BLANKET"], "weight": (500, 5000), "cbm": (300, 3000)},
    # 식품/농산물
    {"goods": "FROZEN TUNA, PACIFIC SALMON", "keywords": ["FROZEN", "TUNA", "SALMON"], "weight": (2000, 20000), "cbm": (1500, 15000)},
    {"goods": "REFINED SUGAR, GLUCOSE SYRUP", "keywords": ["REFINED", "SUGAR", "GLUCOSE"], "weight": (5000, 50000), "cbm": (2000, 20000)},
    {"goods": "SOYBEAN MEAL, ANIMAL FEED", "keywords": ["SOYBEAN", "MEAL", "ANIMAL", "FEED"], "weight": (10000, 100000), "cbm": (5000, 50000)},
    {"goods": "INSTANT NOODLE, DRIED FOOD PRODUCTS", "keywords": ["INSTANT", "NOODLE", "DRIED", "FOOD"], "weight": (1000, 10000), "cbm": (500, 5000)},
    {"goods": "COFFEE BEANS, GREEN UNROASTED", "keywords": ["COFFEE", "BEANS"], "weight": (2000, 20000), "cbm": (1000, 10000)},
    # 자동차 부품
    {"goods": "AUTOMOTIVE ENGINE PARTS, CRANKSHAFT", "keywords": ["AUTOMOTIVE", "ENGINE", "CRANKSHAFT"], "weight": (2000, 20000), "cbm": (1000, 10000)},
    {"goods": "VEHICLE BRAKE SYSTEM COMPONENTS", "keywords": ["VEHICLE", "BRAKE"], "weight": (500, 5000), "cbm": (300, 3000)},
    {"goods": "AUTOMOBILE TYRE, RUBBER TYRE", "keywords": ["AUTOMOBILE", "TYRE", "RUBBER"], "weight": (3000, 30000), "cbm": (2000, 15000)},
    # 건설/인프라
    {"goods": "CEMENT, PORTLAND CEMENT", "keywords": ["CEMENT", "PORTLAND"], "weight": (10000, 100000), "cbm": (3000, 30000)},
    {"goods": "GLASS WOOL INSULATION, ROCK WOOL", "keywords": ["GLASS", "WOOL", "INSULATION"], "weight": (1000, 10000), "cbm": (1000, 10000)},
    {"goods": "PVC PIPE, HDPE PIPE", "keywords": ["PVC", "PIPE", "HDPE"], "weight": (2000, 20000), "cbm": (1500, 15000)},
    # 종이/목재
    {"goods": "KRAFT PAPER, CORRUGATED BOARD", "keywords": ["KRAFT", "PAPER", "CORRUGATED"], "weight": (3000, 30000), "cbm": (2000, 20000)},
    {"goods": "SAWN TIMBER, PLYWOOD", "keywords": ["SAWN", "TIMBER", "PLYWOOD"], "weight": (5000, 50000), "cbm": (3000, 30000)},
]

INCOTERMS_LIST = ["FOB", "CIF", "CFR", "EXW", "DDP", "DAP", "FCA", "CPT", "CIP"]

REQUIRED_DOCS_BASE = ["BILL OF LADING", "COMMERCIAL INVOICE", "PACKING LIST"]
OPTIONAL_DOCS = [
    "CERTIFICATE OF ORIGIN",
    "PHYTOSANITARY CERTIFICATE",
    "HEALTH CERTIFICATE",
    "INSPECTION CERTIFICATE",
    "INSURANCE CERTIFICATE",
    "WEIGHT CERTIFICATE",
    "FUMIGATION CERTIFICATE",
    "ANALYSIS CERTIFICATE",
    "BENEFICIARY'S CERTIFICATE",
    "CUSTOMS DECLARATION",
]

SPECIAL_CONDITIONS_POOL = [
    "ALL DOCUMENTS TO BE PRESENTED IN ENGLISH.",
    "DOCUMENTS TO BE PRESENTED WITHIN 21 DAYS AFTER SHIPMENT.",
    "SEMICONDUCTOR GOODS REQUIRE ESD-SAFE PACKAGING.",
    "GOODS MUST COMPLY WITH FDA REGULATIONS.",
    "COUNTRY OF ORIGIN MUST BE CLEARLY STATED ON ALL DOCUMENTS.",
    "GOODS MUST BE ACCOMPANIED BY A MANUFACTURER'S WARRANTY CERTIFICATE.",
    "THIRD PARTY INSPECTION REQUIRED BEFORE SHIPMENT.",
    "SHIPMENT MUST BE COVERED BY MARINE CARGO INSURANCE.",
    "ALL PACKING MATERIALS MUST BE FREE OF WOOD.",
    "GOODS MUST BE PACKED IN NEW, CLEAN, AND DRY CONTAINERS.",
    "FREIGHT PREPAID BILL OF LADING REQUIRED.",
    "CLEAN ON-BOARD BILL OF LADING REQUIRED.",
    "FULL SET OF 3/3 ORIGINAL BILLS OF LADING REQUIRED.",
    "SHORT FORM BILL OF LADING NOT ACCEPTABLE.",
    "STALE BILLS OF LADING NOT ACCEPTABLE.",
    "CHARTER PARTY BILL OF LADING NOT ACCEPTABLE.",
    "ALL CHARGES OUTSIDE KOREA ARE FOR BUYER'S ACCOUNT.",
    "TRANSHIPMENT IS ALLOWED ONLY VIA SINGAPORE.",
    "GOODS MUST BE FREE FROM PESTS AND DISEASES.",
    "TEMPERATURE CONTROLLED SHIPMENT REQUIRED: -18°C.",
    "GOODS MUST BE CERTIFIED HALAL.",
    "FUMIGATION CERTIFICATE REQUIRED FOR WOODEN PACKAGING.",
    "GOODS MUST COMPLY WITH EU REACH REGULATIONS.",
    "LETTER OF CREDIT IS TRANSFERABLE.",
    "PARTIAL DRAWINGS ARE NOT PERMITTED UNDER THIS L/C.",
    "PAYMENT WILL BE EFFECTED UPON RECEIPT OF CONFORMING DOCUMENTS.",
    "ALL DOCUMENTS MUST SHOW L/C NUMBER AND DATE.",
    "GOODS MUST BE SHIPPED IN 20' OR 40' ISO CONTAINERS.",
    "OVERWEIGHT CONTAINERS NOT ACCEPTABLE.",
    "VENTILATED CONTAINERS REQUIRED FOR AGRICULTURAL GOODS.",
]

DISCREPANCY_SCENARIOS = [
    "COMPLIANT - 모든 조건 일치",
    "COMPLIANT - 모든 조건 일치",
    "COMPLIANT - 모든 조건 일치",
    "COMPLIANT - 모든 조건 일치",
    "COMPLIANT - 모든 조건 일치",
    "DISCREPANT - 적재항이 L/C와 일치하지 않음",
    "DISCREPANT - 양하항이 L/C와 일치하지 않음",
    "DISCREPANT - 수하인 정보가 L/C와 불일치",
    "DISCREPANT - L/C 화물 명세 키워드가 B/L에 누락됨",
    "DISCREPANT - B/L 총중량이 L/C 허용 한도를 초과함",
    "DISCREPANT - B/L 용적이 L/C 허용 한도를 초과함",
    "DISCREPANT - 선적일이 L/C 최종 선적일을 경과함",
    "DISCREPANT - 분할선적 금지 위반",
    "DISCREPANT - 환적 금지 위반",
    "DISCREPANT - 서류 제출 기한 초과",
    "DISCREPANT - B/L 번호 형식 오류",
    "DISCREPANT - 화환어음 금액이 L/C 한도를 초과함",
    "DISCREPANT - 선적자(Shipper) 정보가 L/C 수익자와 불일치",
    "DISCREPANT - 인코텀즈 조건이 L/C와 상이함",
    "DISCREPANT - 필수 서류 누락 (보험증권 미제출)",
]

BL_REF_POOL = (
    [f"IMG_OCR_6_T_BL_{str(i).zfill(6)}" for i in range(2, 20)]
    + [f"IMG_OCR_6_T_BL_{str(i).zfill(6)}" for i in range(100, 500)]
    + [f"IMG_OCR_6_T_BL_{str(i).zfill(6)}" for i in range(1000, 2000)]
)

# ── 날짜 생성 헬퍼 ─────────────────────────────────────────────────────────────

def rand_year():
    return random.randint(2003, 2024)

def rand_date(year):
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"

def rand_expiry(year):
    month = random.randint(6, 12)
    return f"{year}-{month:02d}-30"

def rand_shipment_date(year):
    month = random.randint(1, 11)
    return f"{year}-{month:02d}-{random.randint(1, 28):02d}"

# ── 단일 L/C 생성 ──────────────────────────────────────────────────────────────

def make_lc(idx):
    lc_no = f"LC-2022-{idx:03d}"
    year = rand_year()

    applicant = random.choice(APPLICANTS)
    beneficiary = random.choice(BENEFICIARIES)
    issuing_bank = random.choice(ISSUING_BANKS)
    advising_bank = random.choice(ADVISING_BANKS)

    currency = "USD"
    amount = round(random.choice([
        random.randint(20, 50) * 1000,
        random.randint(50, 200) * 1000,
        random.randint(200, 1000) * 1000,
    ]), 2)
    tolerance_pct = random.choice([5.0, 10.0])

    expiry_date = rand_expiry(year)
    expiry_place = random.choice(EXPIRY_PLACES)

    has_shipment_date = random.random() > 0.3
    latest_shipment_date = rand_shipment_date(year) if has_shipment_date else None

    period_for_presentation = random.choice([14, 21, 21, 21, 30])

    # 적재항 / 양하항
    port_of_loading = random.choice(PORTS)
    port_of_discharge = random.choice([p for p in PORTS if p != port_of_loading])

    incoterms = random.choice(INCOTERMS_LIST)
    partial_shipment = random.choice(["ALLOWED", "ALLOWED", "PROHIBITED"])
    transhipment = random.choice(["ALLOWED", "ALLOWED", "PROHIBITED"])

    consignee = applicant  # 일반적으로 개설의뢰인 = 수하인

    goods = random.choice(GOODS_CATALOG)
    description_of_goods = goods["goods"] if random.random() > 0.1 else None
    w_min, w_max = goods["weight"]
    c_min, c_max = goods["cbm"]
    max_gross_weight_kg = float(random.randint(w_min, w_max))
    max_measurement_cbm = float(random.randint(c_min, c_max))

    payment_terms = "SIGHT"
    usance_days = None

    # 필수 서류
    req_docs = list(REQUIRED_DOCS_BASE)
    n_optional = random.randint(0, 4)
    req_docs += random.sample(OPTIONAL_DOCS, n_optional)

    special_conditions = random.choice(SPECIAL_CONDITIONS_POOL)

    bl_ref = random.choice(BL_REF_POOL)
    scenario = random.choice(DISCREPANCY_SCENARIOS)

    return {
        "lc_no": lc_no,
        "lc_type": "IRREVOCABLE",
        "applicant": applicant,
        "beneficiary": beneficiary,
        "issuing_bank": issuing_bank,
        "advising_bank": advising_bank,
        "currency": currency,
        "amount": amount,
        "tolerance_pct": tolerance_pct,
        "expiry_date": expiry_date,
        "expiry_place": expiry_place,
        "latest_shipment_date": latest_shipment_date,
        "period_for_presentation": period_for_presentation,
        "port_of_loading": port_of_loading,
        "port_of_discharge": port_of_discharge,
        "incoterms": incoterms,
        "partial_shipment": partial_shipment,
        "transhipment": transhipment,
        "consignee": consignee,
        "description_of_goods": description_of_goods,
        "max_gross_weight_kg": max_gross_weight_kg,
        "max_measurement_cbm": max_measurement_cbm,
        "payment_terms": payment_terms,
        "usance_days": usance_days,
        "required_documents": req_docs,
        "special_conditions": special_conditions,
        "_bl_ref": bl_ref,
        "_scenario": scenario,
    }

# ── 메인 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_idx = 11
    end_idx = 110  # inclusive

    generated = []
    for i in range(start_idx, end_idx + 1):
        lc = make_lc(i)
        filename = f"LC-2022-{i:03d}.json"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(lc, f, ensure_ascii=False, indent=2)
        generated.append(filename)
        print(f"[{i - start_idx + 1:03d}/100] {filename} 생성 완료  |  {lc['_scenario'][:40]}")

    print(f"\n총 {len(generated)}개 L/C 파일 생성 완료 → {OUTPUT_DIR}")
