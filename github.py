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

# 🔑 新增 wordfreq 用于加载 100 万高频词
from wordfreq import top_n_list  

lock = threading.Lock()

seen_keywords = set()
seen_schools = set()
results = set()
domains_only = set()

# 基础关键词
base_keywords = [
    "university", "college", "institute", "faculty", "polytechnic", "campus", "school",
    "universidad", "universite", "hochschule", "akademia", "teknik", "technological",
    "indonesia", "philippines", "thailand", "beijing", "hong kong", "tokyo", "malaysia",
    "engineering", "medical", "technology", "science", "national", "china", "japan",
    "korea", "taiwan", "singapore", "brazil", "india", "germany", "france", "canada",
    "primary", "secondary", "elementary", "highschool", "kindergarten", "middle school",
    "faculty", "education", "academy", "universität", "école", "escuela", "школа", "学校", "대학교",
    "università", "universidade", "skola", "skole", "lyceum", "college of", "institute of",
    # 教育相关职位
    "principal", "headmaster", "dean", "professor", "lecturer", "tutor", "counselor",
    "registrar", "chancellor", "provost", "superintendent", "trustee", "faculty member",
    "staff", "coach",
    # 学科专业
    "biotechnology", "data science", "artificial intelligence", "cybersecurity",
    "renewable energy", "urban planning", "marine biology", "forensic science",
    "speech therapy", "social work", "graphic design", "culinary arts", "veterinary science",
    "library science",
    # 建筑设施
    "library", "laboratory", "auditorium", "gymnasium", "dormitory", "cafeteria",
    "research center", "sports complex", "student center", "innovation hub", "media center",
    # 教育阶段类型
    "preschool", "kindergarten", "elementary school", "middle school", "junior high",
    "senior high", "vocational school", "adult education", "special education",
    "online courses", "continuing education", "night school",
    # 学术活动
    "seminar", "workshop", "conference", "exchange program", "study abroad",
    "internship program", "scholarship program", "summer school", "online learning",
    "distance education", "research project", "alumni association",
    # 行政区划
    "village", "hamlet", "neighborhood", "ward", "block", "precinct", "suburb",
    "township", "canton", "parish",
    # 语言文化
    "bilingual", "trilingual", "language center", "cultural center",
    "international school", "immersion program", "heritage school",
    # 其他相关
    "education reform", "curriculum development", "standards",
    "charter school", "magnet school", "alternative school",
    "accreditation", "qs ranking", "times higher education",
    "online platform", "learning management system", "virtual classroom"
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
            items = soup.find_all("div", class_="ActionListItem typeahead-result js-school-autocomplete-result-selection")

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
                            with lock:
                                if entry not in results:
                                    results.add(entry)
                                    domains_only.add(domain)
                                    print("[+] 发现学校:", entry)
                                    results_file.write(entry + "\n")
                                    domains_file.write(domain + "\n")
                                    results_file.flush()
                                    domains_file.flush()

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
    open("results_full.txt", "w", encoding="utf-8").close()
    open("results_domains.txt", "w", encoding="utf-8").close()

    results_file = open("results_full.txt", "a", encoding="utf-8")
    domains_file = open("results_domains.txt", "a", encoding="utf-8")

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

    results_file.close()
    domains_file.close()

    print("[✓] 完成。结果保存到 results_full.txt 和 results_domains.txt")
