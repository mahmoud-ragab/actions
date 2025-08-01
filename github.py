import requests
import threading
import time
import re
from bs4 import BeautifulSoup
from queue import Queue
import itertools
import string

lock = threading.Lock()

seen_keywords = set()
seen_schools = set()
results = set()
domains_only = set()

# 之前的初始关键词
base_keywords = [
    "university", "college", "institute", "faculty", "polytechnic", "campus", "school",
    "universidad", "universite", "hochschule", "akademia", "teknik", "technological",
    "indonesia", "philippines", "thailand", "beijing", "hong kong", "tokyo", "malaysia",
    "engineering", "medical", "technology", "science", "national", "china", "japan",
    "korea", "taiwan", "singapore", "brazil", "india", "germany", "france", "canada",
    "primary", "secondary", "elementary", "highschool", "kindergarten", "middle school",
    "faculty", "education", "academy", "universität", "école", "escuela", "школа", "学校", "대학교",
    "università", "universidade", "skola", "skole", "lyceum", "college of", "institute of",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"
]

# 新增：生成长度3-5的字母组合（顺序遍历）
def generate_ordered_keywords(min_len=3, max_len=5):
    chars = string.ascii_lowercase
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(chars, repeat=length):
            yield ''.join(combo)

# 把生成的组合加到初始关键词里
initial_keywords = base_keywords.copy()
initial_keywords.extend(generate_ordered_keywords(3, 5))

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
        keyword = q.get()
        if keyword is None:
            break
        search_keyword(keyword)
        q.task_done()

def save_results():
    with lock:
        with open("results_full.txt", "w", encoding="utf-8") as f:
            for line in sorted(results):
                f.write(line + "\n")
        with open("results_domains.txt", "w", encoding="utf-8") as f:
            for line in sorted(domains_only):
                f.write(line + "\n")

def search_keyword(keyword):
    if keyword in seen_keywords:
        return
    seen_keywords.add(keyword)
    try:
        print(f"[*] Searching: {keyword}")
        url = BASE_URL + requests.utils.quote(keyword)
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"[!] Failed ({response.status_code}): {keyword}")
            return
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.find_all("div", class_="ActionListItem typeahead-result js-school-autocomplete-result-selection")

        for item in items:
            school = item.get("data-school-name")
            domains_raw = item.get("data-email-domains")

            if not school or school in seen_schools:
                continue

            seen_schools.add(school)

            if domains_raw and "[]" not in domains_raw:
                domain_matches = re.findall(r'"(.*?)"', domains_raw)
                for domain in domain_matches:
                    entry = f"{domain}--{school}"
                    with lock:
                        if entry not in results:
                            results.add(entry)
                            domains_only.add(domain)
                            print("[+] Found:", entry)

            # 拆词继续递归关键词，不变
            words = re.split(r"[,\s\-–]", school)
            for word in words:
                word = word.strip().lower()
                if word and word not in seen_keywords and 2 < len(word) < 40:
                    q.put(word)

    except Exception as e:
        print(f"[!] Error processing {keyword}: {e}")

if __name__ == "__main__":
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
        print("[*] Interrupted!")

    for _ in threads:
        q.put(None)
    for t in threads:
        t.join()

    save_results()
    print("[✓] Done. Results saved to results_full.txt and results_domains.txt")
