import requests
import re
import time
from queue import Queue
from threading import Lock, Thread

COOKIE = "__Host-user_session_same_site=Dl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k;_device_id=f2e8347acf71d1d5984b1bb5503df6e8;_gh_sess=xfjiHQrUEDLljKsd%2BeW2Fz7UOiz2qGszjpE9%2FCP68HFCYsbkAH8esvQug4XmA2SNJvseuQbgdE3%2B89gC80OwzixCF9J%2FqjE5y3chSqvf30ACriCd%2BxLT1cqyMOEBDpe1Lv2IJ%2BH2FVe1c2Kch4%2Fo6iBzt26mYRJXm8nsFkAsHmmz8glUPhxl4gfItJa5%2BmHrKYRTIUwm%2BO2T4FUY%2BtkV7ov83F55fLefRBVU1n91yT8KnYN2UZ5SyOAQtK1FitX3NpSOJgkX0dduU4zknoE5GaRcyoIr5TJQwyE7SRVmULvJjOKwFB8PPoTny887H%2FK0Z%2BeUn9Z2s9YB1QgUQjlg7CZZ414MbMO1cNfJew%3D%3D--1f8440q3WIvz5wcp--pUquBUHEktxIidsI9BcUCQ%3D%3D;_octo=GH1.1.1220093520.1750220192;color_mode=%7B%22color_mode%22%3A%22auto%22%2C%22light_theme%22%3A%7B%22name%22%3A%22light%22%2C%22color_mode%22%3A%22light%22%7D%2C%22dark_theme%22%3A%7B%22name%22%3A%22dark%22%2C%22color_mode%22%3A%22dark%22%7D%7D;cpu_bucket=xlg;dotcom_user=mahmoud-ragab;GHCC=Required:1-Analytics:1-SocialMedia:1-Advertising:1;logged_in=yes;MicrosoftApplicationsTelemetryDeviceId=ea18b101-56c1-4dd0-98bd-1385451cad05;preferred_color_mode=light;saved_user_sessions=82536688%3AUIkX4SyFfoloKdbOrUSizOOZq7snwfIm7HoYQ1cAz3qtU3Sq%7C18014637%3ADl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k;tz=Asia%2FShanghai;user_session=Dl9dHRcLP09rGw6VxYXJnvAY2G0tn6f5oCWdlVdcKAF-M87k"

HEADERS = {
    "accept": "text/fragment+html",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "referer": "https://github.com/settings/education/benefits",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "cookie": COOKIE,
}

BASE_URL = "https://github.com/settings/education/developer_pack_applications/schools?q={}"

initial_keywords = [
    "school", "college", "university", "institut", "schule", "escuela",
    "école", "universität", "faculdade", "università", "学院", "学校",
    "جامعة", "โรงเรียน", "विद्यालय", "instituto", "campus", "academy",
    "kindergarten", "elementary", "secondary", "high school",
    "college", "universidade", "université", "università",

    # 国家名
    "china", "india", "germany", "france", "spain", "italy", "brazil",
    "japan", "russia", "mexico", "canada", "australia", "south africa",
    "egypt", "turkey", "netherlands", "sweden", "norway", "finland",

    # 城市名（部分）
    "beijing", "shanghai", "delhi", "mumbai", "berlin", "paris", "madrid",
    "rome", "sao paulo", "tokyo", "moscow", "toronto", "sydney",

    # 教育相关词
    "faculty", "department", "institute", "academy", "polytechnic",
    "technical", "vocational", "research", "science", "arts", "law",
    "medical", "engineering"
]

queue = Queue()
visited_keywords = set()
visited_domains = set()
lock = Lock()

def extract_schools_domains(html):
    pattern = re.compile(
        r'data-school-name="(.*?)".*?data-email-domains="\[\[(.*?)\]\]"',
        re.DOTALL
    )
    results = []
    for match in pattern.finditer(html):
        school_name = match.group(1)
        raw_domains = match.group(2)
        domains = re.findall(r'&quot;(.*?)&quot;', raw_domains)
        if domains:
            for domain in domains:
                results.append((domain, school_name))
    return results

def extract_and_expand_keywords(school_name):
    words = re.findall(r"[a-zA-Z\u00C0-\u017F\u4e00-\u9fff]+", school_name)
    keywords = set()
    filtered = [w.lower() for w in words if len(w) > 2]
    for length in range(1, 4):
        for i in range(len(filtered) - length + 1):
            phrase = " ".join(filtered[i:i+length])
            keywords.add(phrase)
    return keywords

def fetch_and_process(keyword):
    with lock:
        if keyword in visited_keywords:
            return set()
        visited_keywords.add(keyword)
    print(f"[*] 搜索关键词：{keyword}")
    url = BASE_URL.format(requests.utils.quote(keyword))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"[!] 请求失败 {resp.status_code}，关键词：{keyword}")
            return set()
        html = resp.text
    except Exception as e:
        print(f"[!] 请求异常 {e}，关键词：{keyword}")
        return set()

    results = extract_schools_domains(html)
    new_keywords = set()

    with lock:
        with open("schools_domains.txt", "a", encoding="utf-8") as f:
            for domain, school in results:
                if domain not in visited_domains:
                    visited_domains.add(domain)
                    line = f"{domain}--{school}"
                    print(line)
                    f.write(line + "\n")
            f.flush()

    for _, school in results:
        expanded = extract_and_expand_keywords(school)
        new_keywords.update(expanded)

    return new_keywords

def worker():
    while True:
        keyword = queue.get()
        if keyword is None:
            break
        new_keywords = fetch_and_process(keyword)
        with lock:
            for nk in new_keywords:
                if nk not in visited_keywords and nk not in list(queue.queue):
                    queue.put(nk)
        time.sleep(1)  # 防封，适当延迟
        queue.task_done()

def main():
    for kw in initial_keywords:
        queue.put(kw)

    thread_count = 10
    threads = []
    for _ in range(thread_count):
        t = Thread(target=worker)
        t.daemon = True
        t.start()
        threads.append(t)

    queue.join()

    # 结束线程
    for _ in range(thread_count):
        queue.put(None)
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
