import requests
import threading
import time
import re
from bs4 import BeautifulSoup
from queue import Queue
import itertools
import string
import zipfile
import io
import csv

import os

# 🔑 新增 wordfreq 用于加载 100 万高频词
from wordfreq import top_n_list

lock = threading.Lock()

seen_keywords = set()
seen_schools = set()
results = set()
domains_only = set()

# 结果文件路径（使用脚本所在目录的绝对路径）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FULL_FILE = os.path.join(SCRIPT_DIR, "results_full.txt")
RESULTS_DOMAINS_FILE = os.path.join(SCRIPT_DIR, "results_domains.txt")

def load_existing_results():
    """加载已有结果，支持断点续传"""
    global results, domains_only, seen_schools
    try:
        with open(RESULTS_FULL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "--" in line:
                    results.add(line)
                    parts = line.split("--", 1)
                    if len(parts) == 2:
                        domains_only.add(parts[0])
                        seen_schools.add(parts[1])
        print(f"[*] 已加载 {len(results)} 条历史结果")
    except FileNotFoundError:
        print("[*] 未找到历史结果文件，将创建新文件")
    except Exception as e:
        print(f"[!] 加载历史结果失败: {e}")

def save_result(entry, domain):
    """实时保存单条结果到文件"""
    with lock:
        if entry not in results:
            results.add(entry)
            domains_only.add(domain)
            print("[+] 发现学校:", entry)
            try:
                with open(RESULTS_FULL_FILE, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # 强制写入磁盘
                with open(RESULTS_DOMAINS_FILE, "a", encoding="utf-8") as f:
                    f.write(domain + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # 强制写入磁盘
            except Exception as e:
                print(f"[!] 保存失败: {e}")
            return True
    return False

# 基础关键词
base_keywords = [
    # ==================== 英语核心教育词 ====================
    "university", "college", "institute", "faculty", "polytechnic", "campus", "school",
    "academy", "education", "educational", "academic", "academics", "seminary", "conservatory",
    "university of", "college of", "institute of", "school of", "faculty of",
    "state university", "community college", "technical college", "liberal arts",
    "research university", "private university", "public university",
    
    # ==================== 多语言"大学/学校"词汇 ====================
    # 西班牙语
    "universidad", "colegio", "escuela", "instituto", "facultad", "politécnico",
    # 法语
    "université", "universite", "école", "ecole", "lycée", "lycee", "collège", "college", "faculté",
    # 德语
    "universität", "universitaet", "hochschule", "fachhochschule", "schule", "akademie", "gymnasium",
    # 意大利语
    "università", "universita", "politecnico", "istituto", "scuola", "liceo", "accademia",
    # 葡萄牙语
    "universidade", "faculdade", "instituto", "escola", "colégio", "politécnica",
    # 荷兰语
    "universiteit", "hogeschool", "academie", "school",
    # 波兰语
    "uniwersytet", "politechnika", "akademia", "szkoła", "instytut",
    # 捷克语/斯洛伐克语
    "univerzita", "vysoká škola", "akademie",
    # 俄语
    "университет", "институт", "академия", "школа", "факультет", "колледж",
    # 乌克兰语
    "університет", "інститут", "академія",
    # 土耳其语
    "üniversitesi", "üniversite", "fakültesi", "okulu", "enstitüsü", "akademi",
    # 阿拉伯语
    "جامعة", "كلية", "معهد", "مدرسة", "أكاديمية",
    # 波斯语
    "دانشگاه", "دانشکده",
    # 希伯来语
    "אוניברסיטה", "מכללה",
    # 印地语
    "विश्वविद्यालय", "महाविद्यालय", "संस्थान", "विद्यालय",
    # 孟加拉语
    "বিশ্ববিদ্যালয়", "কলেজ",
    # 泰语
    "มหาวิทยาลัย", "วิทยาลัย", "สถาบัน",
    # 越南语
    "đại học", "trường", "học viện", "cao đẳng",
    # 印尼语/马来语
    "universitas", "institut", "sekolah", "politeknik", "akademi", "kolej",
    # 菲律宾语
    "pamantasan", "kolehiyo", "unibersidad",
    # 日语
    "大学", "学院", "専門学校", "高等学校", "中学校", "小学校", "学園", "学校",
    # 韩语
    "대학교", "대학", "학교", "학원", "전문대학", "고등학교",
    # 中文
    "学校", "大学", "学院", "中学", "小学", "高中", "职业学校", "师范", "理工", "科技大学",
    # 北欧语言
    "universitet", "högskola", "skola", "skole", "koulu", "yliopisto", "ammattikorkeakoulu",
    # 希腊语
    "πανεπιστήμιο", "σχολή", "ακαδημία",
    # 罗马尼亚语
    "universitate", "facultate", "academie", "institut", "colegiu",
    # 匈牙利语
    "egyetem", "főiskola", "akadémia",
    
    # ==================== 著名学校缩写 ====================
    "MIT", "UCLA", "USC", "NYU", "UCSD", "UCSB", "UCI", "UCB", "UIUC", "UMICH",
    "CMU", "Caltech", "Stanford", "Harvard", "Yale", "Princeton", "Columbia",
    "Cornell", "Brown", "Dartmouth", "UPenn", "Duke", "Northwestern", "JHU",
    "Georgia Tech", "Purdue", "OSU", "PSU", "UMass", "UConn", "Rutgers",
    "HKUST", "HKU", "CUHK", "CityU", "PolyU",  # 香港
    "NUS", "NTU", "SMU", "SUTD",  # 新加坡
    "PKU", "THU", "Tsinghua", "Peking", "Fudan", "SJTU", "ZJU", "USTC", "NJU",  # 中国大陆
    "NTU Taiwan", "NCTU", "NTHU", "NCU",  # 台湾
    "UTokyo", "Kyoto", "Osaka", "Tohoku", "Nagoya", "Waseda", "Keio",  # 日本
    "SNU", "KAIST", "POSTECH", "Yonsei", "Korea University",  # 韩国
    "ETH", "EPFL",  # 瑞士
    "Oxford", "Cambridge", "Imperial", "UCL", "LSE", "Edinburgh", "Manchester",  # 英国
    "TUM", "LMU", "RWTH", "Heidelberg", "Humboldt",  # 德国
    "Sorbonne", "ENS", "Polytechnique", "Sciences Po",  # 法国
    "UofT", "McGill", "UBC", "Waterloo", "Alberta",  # 加拿大
    "ANU", "Melbourne", "Sydney", "UNSW", "Monash", "Queensland",  # 澳大利亚
    "IIT", "IISc", "AIIMS", "BITS", "NIT", "IIIT",  # 印度
    "USP", "Unicamp", "UFRJ", "UNESP",  # 巴西
    "UNAM", "Tecnológico de Monterrey", "Tec",  # 墨西哥
    
    # ==================== 教育阶段类型 ====================
    "preschool", "pre-school", "kindergarten", "nursery", "daycare",
    "elementary school", "primary school", "grade school",
    "middle school", "junior high", "intermediate school",
    "high school", "senior high", "secondary school", "preparatory",
    "vocational school", "trade school", "technical school", "vocational training",
    "community college", "junior college", "two-year college",
    "graduate school", "postgraduate", "doctoral program", "PhD program",
    "adult education", "continuing education", "lifelong learning",
    "special education", "special needs", "inclusive education",
    "online school", "virtual school", "cyber school", "distance learning",
    "night school", "evening classes", "weekend school",
    "boarding school", "day school", "residential school",
    "charter school", "magnet school", "alternative school", "montessori",
    "homeschool", "home education",
    
    # ==================== 学科专业（大幅扩充） ====================
    # 工程类
    "engineering", "mechanical engineering", "electrical engineering", "civil engineering",
    "chemical engineering", "aerospace engineering", "biomedical engineering",
    "computer engineering", "software engineering", "industrial engineering",
    "environmental engineering", "materials engineering", "nuclear engineering",
    # 理学类
    "science", "physics", "chemistry", "biology", "mathematics", "statistics",
    "astronomy", "geology", "geography", "environmental science", "earth science",
    "marine science", "atmospheric science", "materials science",
    # 计算机与信息
    "computer science", "information technology", "data science", "artificial intelligence",
    "machine learning", "cybersecurity", "information systems", "software development",
    # 医学健康
    "medicine", "medical", "nursing", "pharmacy", "dentistry", "veterinary",
    "public health", "epidemiology", "biomedical", "clinical", "healthcare",
    "physical therapy", "occupational therapy", "speech therapy", "nutrition",
    "psychology", "psychiatry", "neuroscience",
    # 商业管理
    "business", "management", "MBA", "finance", "accounting", "economics",
    "marketing", "entrepreneurship", "international business", "supply chain",
    "human resources", "organizational behavior", "operations management",
    # 法律政治
    "law", "legal studies", "jurisprudence", "political science", "public policy",
    "international relations", "public administration", "diplomacy",
    # 人文社科
    "arts", "humanities", "liberal arts", "philosophy", "history", "literature",
    "linguistics", "anthropology", "sociology", "archaeology", "religious studies",
    "theology", "divinity", "cultural studies", "gender studies", "ethnic studies",
    # 艺术设计
    "fine arts", "visual arts", "performing arts", "music", "dance", "theater", "theatre",
    "film", "cinema", "photography", "graphic design", "industrial design",
    "fashion design", "interior design", "architecture", "urban planning",
    # 传媒新闻
    "journalism", "media", "communication", "broadcasting", "advertising",
    "public relations", "digital media", "multimedia",
    # 农业环境
    "agriculture", "agronomy", "horticulture", "forestry", "fisheries",
    "animal science", "food science", "environmental studies", "sustainability",
    # 其他专业
    "education", "pedagogy", "teaching", "curriculum", "instructional design",
    "library science", "information science", "archival studies",
    "social work", "counseling", "criminal justice", "criminology",
    "hospitality", "tourism", "hotel management", "culinary arts",
    "aviation", "aeronautics", "maritime", "nautical",
    "sports science", "kinesiology", "physical education", "athletics",
    
    # ==================== 地理方位词 ====================
    "east", "west", "north", "south", "central", "eastern", "western",
    "northern", "southern", "northeast", "northwest", "southeast", "southwest",
    "upper", "lower", "greater", "metropolitan", "regional", "provincial",
    
    # ==================== 国家地区（补充） ====================
    # 亚洲
    "china", "japan", "korea", "taiwan", "hong kong", "macau", "singapore", "malaysia",
    "thailand", "vietnam", "indonesia", "philippines", "india", "pakistan", "bangladesh",
    "sri lanka", "nepal", "myanmar", "cambodia", "laos", "brunei", "mongolia",
    "kazakhstan", "uzbekistan", "iran", "iraq", "saudi arabia", "uae", "qatar", "kuwait",
    "israel", "turkey", "jordan", "lebanon", "oman", "bahrain", "yemen", "afghanistan",
    # 欧洲
    "germany", "france", "uk", "britain", "england", "scotland", "wales", "ireland",
    "italy", "spain", "portugal", "netherlands", "belgium", "switzerland", "austria",
    "poland", "czech", "slovakia", "hungary", "romania", "bulgaria", "greece", "croatia",
    "serbia", "slovenia", "ukraine", "russia", "finland", "sweden", "norway", "denmark",
    "iceland", "estonia", "latvia", "lithuania", "belarus", "moldova", "albania", "cyprus",
    # 美洲
    "usa", "america", "canada", "mexico", "brazil", "argentina", "chile", "colombia",
    "peru", "venezuela", "ecuador", "bolivia", "paraguay", "uruguay", "panama", "costa rica",
    "guatemala", "cuba", "dominican", "puerto rico", "jamaica", "haiti", "honduras",
    # 非洲
    "egypt", "south africa", "nigeria", "kenya", "morocco", "algeria", "tunisia", "ghana",
    "ethiopia", "tanzania", "uganda", "rwanda", "senegal", "cameroon", "ivory coast",
    "zimbabwe", "zambia", "botswana", "namibia", "mozambique", "angola", "sudan",
    # 大洋洲
    "australia", "new zealand", "fiji", "papua new guinea",
    
    # ==================== 主要城市（补充） ====================
    "beijing", "shanghai", "guangzhou", "shenzhen", "hangzhou", "nanjing", "wuhan", "chengdu", "xian",
    "tokyo", "osaka", "kyoto", "nagoya", "fukuoka", "sapporo", "yokohama", "kobe",
    "seoul", "busan", "incheon", "daegu", "daejeon",
    "taipei", "kaohsiung", "taichung", "tainan",
    "new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia", "san antonio",
    "san diego", "dallas", "san jose", "austin", "boston", "seattle", "denver", "atlanta",
    "london", "manchester", "birmingham", "liverpool", "edinburgh", "glasgow", "bristol",
    "paris", "lyon", "marseille", "toulouse", "nice", "bordeaux", "strasbourg",
    "berlin", "munich", "frankfurt", "hamburg", "cologne", "stuttgart", "düsseldorf",
    "rome", "milan", "naples", "turin", "florence", "venice", "bologna",
    "madrid", "barcelona", "valencia", "seville", "malaga", "bilbao",
    "moscow", "st petersburg", "novosibirsk", "yekaterinburg", "kazan",
    "mumbai", "delhi", "bangalore", "chennai", "kolkata", "hyderabad", "pune", "ahmedabad",
    "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra",
    "toronto", "vancouver", "montreal", "calgary", "ottawa", "edmonton",
    "sao paulo", "rio de janeiro", "brasilia", "salvador", "fortaleza",
    "mexico city", "guadalajara", "monterrey", "puebla", "tijuana",
    "cairo", "johannesburg", "cape town", "lagos", "nairobi", "casablanca", "tunis",
    "dubai", "abu dhabi", "riyadh", "jeddah", "doha", "kuwait city", "muscat",
    "istanbul", "ankara", "izmir", "tehran", "baghdad", "tel aviv", "jerusalem",
    "bangkok", "kuala lumpur", "jakarta", "manila", "ho chi minh", "hanoi", "yangon",
    
    # ==================== 教育相关职位 ====================
    "principal", "headmaster", "headmistress", "dean", "professor", "lecturer",
    "instructor", "tutor", "counselor", "advisor", "mentor", "teacher",
    "registrar", "chancellor", "provost", "president", "vice president",
    "superintendent", "trustee", "faculty member", "staff", "coach",
    "researcher", "postdoc", "fellow", "scholar", "alumnus", "alumni",
    
    # ==================== 学术活动 ====================
    "seminar", "workshop", "conference", "symposium", "colloquium", "lecture",
    "exchange program", "study abroad", "student exchange", "international exchange",
    "internship", "co-op", "practicum", "fieldwork", "clinical rotation",
    "scholarship", "fellowship", "grant", "funding", "financial aid",
    "summer school", "winter school", "intensive course", "boot camp",
    "online learning", "e-learning", "MOOC", "distance education", "blended learning",
    "research project", "thesis", "dissertation", "capstone",
    "alumni association", "student union", "student government",
    "graduation", "commencement", "convocation", "matriculation",
    
    # ==================== 设施建筑 ====================
    "library", "laboratory", "lab", "auditorium", "gymnasium", "gym",
    "dormitory", "dorm", "residence hall", "student housing",
    "cafeteria", "dining hall", "student center", "campus center",
    "research center", "innovation hub", "incubator", "accelerator",
    "sports complex", "athletic center", "stadium", "arena",
    "media center", "computer lab", "makerspace", "fab lab",
    "observatory", "planetarium", "museum", "gallery", "theater",
    "health center", "clinic", "counseling center", "career center",
    
    # ==================== 认证排名 ====================
    "accreditation", "accredited", "certified", "recognized", "approved",
    "AACSB", "ABET", "EQUIS", "AMBA", "WASC", "SACS", "NEASC",
    "QS ranking", "Times Higher Education", "THE", "ARWU", "Shanghai ranking",
    "US News", "world ranking", "national ranking", "top university",
    
    # ==================== 教育域名后缀关键词 ====================
    "edu", "ac", "edu.cn", "edu.tw", "edu.hk", "edu.sg", "edu.my",
    "edu.au", "edu.br", "edu.mx", "edu.ar", "edu.co", "edu.pe",
    "edu.in", "edu.pk", "edu.bd", "edu.np", "edu.lk",
    "edu.eg", "edu.za", "edu.ng", "edu.ke", "edu.gh",
    "edu.tr", "edu.sa", "edu.ae", "edu.qa", "edu.jo",
    "ac.uk", "ac.jp", "ac.kr", "ac.th", "ac.id", "ac.nz", "ac.za", "ac.il", "ac.ir",
    
    # ==================== 常见学校命名模式 ====================
    "national university", "state university", "federal university",
    "city university", "metropolitan university", "regional university",
    "technical university", "technological university", "technology university",
    "open university", "distance university", "virtual university",
    "catholic university", "christian university", "islamic university", "buddhist university",
    "women's university", "men's college", "military academy", "naval academy", "air force academy",
    "teachers college", "normal university", "pedagogical university",
    "medical university", "health sciences university", "dental school",
    "law school", "business school", "engineering school", "art school", "music school",
    "agricultural university", "maritime university", "aviation university",
    
    # ==================== 其他有用词汇 ====================
    "affiliated", "branch campus", "satellite campus", "extension",
    "consortium", "alliance", "network", "system", "foundation",
    "undergraduate", "graduate", "postgraduate", "doctoral", "professional",
    "bachelor", "master", "doctorate", "diploma", "certificate", "degree",
    "enrollment", "admission", "application", "registration", "orientation",
    "curriculum", "syllabus", "course", "program", "major", "minor", "concentration",
    "credit", "GPA", "transcript", "academic record",
    "semester", "trimester", "quarter", "academic year", "term",
    "tuition", "fees", "scholarship", "bursary", "stipend", "loan",
]

# 生成所有3字母组合关键词
def generate_letter_combinations(min_len=3, max_len=3):
    chars = string.ascii_lowercase
    for length in range(min_len, max_len+1):
        for combo in itertools.product(chars, repeat=length):
            yield ''.join(combo)

# GeoNames在线加载国家、省/州关键词
def load_countries():
    url = "https://download.geonames.org/export/dump/countryInfo.txt"
    countries = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 5:
                countries.append(parts[4].lower())
    except Exception as e:
        print(f"[!] 加载国家失败: {e}")
    return countries

def load_admin1():
    url = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
    admins = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                admins.append(parts[1].lower())
    except Exception as e:
        print(f"[!] 加载省/州失败: {e}")
    return admins

def load_cities():
    url = "https://download.geonames.org/export/dump/cities1000.zip"
    cities = []
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        with z.open("cities1000.txt") as f:
            for line in io.TextIOWrapper(f, encoding='utf-8'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    city = parts[1].strip().lower()
                    if city:
                        cities.append(city)
    except Exception as e:
        print(f"[!] 加载城市失败: {e}")
    return cities

def load_geo_keywords():
    print("[*] 加载国家关键词...")
    countries = load_countries()
    print(f"[*] 国家数: {len(countries)}")
    print("[*] 加载省/州关键词...")
    admins = load_admin1()
    print(f"[*] 省/州数: {len(admins)}")
    print("[*] 加载城市关键词（大文件，需耐心）...")
    cities = load_cities()
    print(f"[*] 城市数: {len(cities)}")

    all_geo = set()
    all_geo.update(countries)
    all_geo.update(admins)
    all_geo.update(cities)
    return list(all_geo)

# ==========================================================
# 这里替换关键词初始化逻辑：加载 GitHub 46 万 + wordfreq 100 万
# ==========================================================
def load_big_wordlist():
    print("[*] 正在加载 GitHub 词表...")
    url = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    words_github = set(resp.text.splitlines())

    print("[*] 正在加载 wordfreq 高频词...")
    words_wordfreq = set(top_n_list("en", 1000000))

    merged = words_github | words_wordfreq
    print(f"[*] GitHub + wordfreq 合并后关键词数: {len(merged)}")
    return merged

print("[*] 初始化关键词...")
initial_keywords = set(base_keywords)
initial_keywords.update(generate_letter_combinations(3,3))
initial_keywords.update(load_geo_keywords())
initial_keywords.update(load_big_wordlist())  # 🔥 加入 150 万词
initial_keywords = list(initial_keywords)
print(f"[*] 最终初始关键词总数: {len(initial_keywords)}")

# ==========================================================
# 以下部分保持原样（GitHub 搜索逻辑）
# ==========================================================

HEADERS = {
    "accept": "text/fragment+html",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "referer": "https://github.com/settings/education/benefits",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "cookie": "__Host-user_session_same_site=Dl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k;_device_id=f2e8347acf71d1d5984b1bb5503df6e8;_gh_sess=xfjiHQrUEDLljKsd%2BeW2Fz7UOiz2qGszjpE9%2FCP68HFCYsbkAH8esvQug4XmA2SNJvseuQbgdE3%2B89gC80OwzixCF9J%2FqjE5y3chSqvf30ACriCd%2BxLT1cqyMOEBDpe1Lv2IJ%2BH2FVe1c2Kch4%2Fo6iBzt26mYRJXm8nsFkAsHmmz8glUPhxl4gfItJa5%2BmHrKYRTIUwm%2BO2T4FUY%2BtkV7ov83F55fLefRBVU1n91yT8KnYN2UZ5SyOAQtK1FitX3NpSOJgkX0dduU4zknoE5GaRcyoIr5TJQwyE7SRVmULvJjOKwFB8PPoTny887H%2FK0Z%2BeUn9Z2s9YB1QgUQjlg7CZZ414MbMO1cNfJew%3D%3D--1f8440q3WIvz5wcp--pUquBUHEktxIidsI9BcUCQ%3D%3D;_octo=GH1.1.1220093520.1750220192;color_mode=%7B%22color_mode%22%3A%22auto%22%2C%22light_theme%22%3A%7B%22name%22%3A%22light%22%2C%22color_mode%22%3A%22light%22%7D%2C%22dark_theme%22%3A%7B%22name%22%3A%22dark%22%2C%22color_mode%22%3A%22dark%22%7D%7D;cpu_bucket=xlg;dotcom_user=mahmoud-ragab;GHCC=Required:1-Analytics:1-SocialMedia:1-Advertising:1;logged_in=yes;MicrosoftApplicationsTelemetryDeviceId=ea18b101-56c1-4dd0-98bd-1385451cad05;preferred_color_mode=light;saved_user_sessions=82536688%3AUIkX4SyFfoloKdbOrUSizOOZq7snwfIm7HoYQ1cAz3qtU3Sq%7C18014637%3ADl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k;tz=Asia%2FShanghai;user_session=Dl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k"
}

BASE_URL = "https://github.com/settings/education/developer_pack_applications/schools?q="

q = Queue()
num_threads = 30
threads = []

def worker():
    while True:
        kw = q.get()
        if kw is None:
            break
        search_keyword(kw)
        q.task_done()

def search_keyword(keyword):
    if keyword in seen_keywords:
        return
    seen_keywords.add(keyword)

    first_429 = True
    while True:
        try:
            print(f"[*] 搜索关键词: {keyword}")
            url = BASE_URL + requests.utils.quote(keyword)
            resp = requests.get(url, headers=HEADERS, timeout=15)

            if resp.status_code == 429:
                if first_429:
                    print(f"[!] 被限流 429，关键词'{keyword}'休眠70分钟...")
                    time.sleep(4200)
                    first_429 = False
                else:
                    print(f"[!] 再次限流 429，关键词'{keyword}'休眠5分钟...")
                    time.sleep(300)
                continue

            if resp.status_code != 200:
                print(f"[!] 请求失败 {resp.status_code}，关键词: {keyword}")
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            # 使用 data-school-name 属性选择，更稳定
            items = soup.find_all(attrs={"data-school-name": True})

            for item in items:
                school = item.get("data-school-name")
                domains_raw = item.get("data-email-domains")

                if not school or school in seen_schools:
                    continue

                seen_schools.add(school)

                if domains_raw and domains_raw != "[]":
                    domains_str = domains_raw.replace("&quot;", '"').replace("false", "False").replace("true", "True")
                    try:
                        domains_list = eval(domains_str)
                    except Exception as e:
                        print(f"[!] 域名解析失败: {e}")
                        domains_list = []

                    if domains_list:
                        for domain_info in domains_list:
                            domain = domain_info[0]
                            entry = f"{domain}--{school}"
                            save_result(entry, domain)

                    # 拆分学校名递归加入关键词队列
                    words = re.split(r"[,\s\-–]", school)
                    for w in words:
                        w = w.strip().lower()
                        if w and w not in seen_keywords and 2 < len(w) < 40:
                            q.put(w)

                else:
                    words = re.split(r"[,\s\-–]", school)
                    for w in words:
                        w = w.strip().lower()
                        if w and w not in seen_keywords and 2 < len(w) < 40:
                            q.put(w)
            break

        except requests.exceptions.RequestException as e:
            if first_429:
                print(f"[!] 请求异常 {keyword}: {e}，休眠70分钟重试")
                time.sleep(4200)
                first_429 = False
            else:
                print(f"[!] 请求异常 {keyword}: {e}，休眠5分钟重试")
                time.sleep(300)

if __name__ == "__main__":
    print(f"[*] 结果将保存到: {RESULTS_FULL_FILE}")
    print(f"[*] 域名将保存到: {RESULTS_DOMAINS_FILE}")
    
    # 加载已有结果（断点续传）
    load_existing_results()
    
    # 如果没有历史文件则创建
    if not results:
        open(RESULTS_FULL_FILE, "a", encoding="utf-8").close()
        open(RESULTS_DOMAINS_FILE, "a", encoding="utf-8").close()

    for kw in initial_keywords:
        q.put(kw)

    for _ in range(num_threads):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        threads.append(t)

    try:
        q.join()
    except KeyboardInterrupt:
        print("[*] 手动终止！")

    for _ in threads:
        q.put(None)
    for t in threads:
        t.join()

    print(f"[✓] 完成！共发现 {len(results)} 个学校")
    print(f"[✓] 结果已实时保存到 {RESULTS_FULL_FILE} 和 {RESULTS_DOMAINS_FILE}")
