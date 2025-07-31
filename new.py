import requests
import concurrent.futures
import threading
import time

lock = threading.Lock()

def check_namecheap(domain):
    """
    Namecheap官方接口查询域名是否可注册
    返回 True 可注册，False 不可注册
    """
    url = "https://ap.www.namecheap.com/domains/check"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Origin": "https://www.namecheap.com",
        "Referer": "https://www.namecheap.com/"
    }
    payload = {
        "DomainList": [domain]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if "Domains" in data and data["Domains"]:
                status = data["Domains"][0].get("IsRegistered")
                return not status  # False表示已注册，True表示可注册
        return False
    except Exception as e:
        print(f"⚠️ Namecheap 查询 {domain} 失败: {e}")
        return None

def process_domain(domain, output_file):
    is_available = check_namecheap(domain)
    if is_available:
        print(f"域名 {domain} 可注册")
        with lock, open(output_file, "a", encoding="utf-8") as out_file:
            out_file.write(domain + "\n")
    elif is_available is None:
        print(f"域名 {domain} 查询失败")
    else:
        print(f"域名 {domain} 已注册")

def main():
    file_path = "domain.txt"
    output_file = "available_namecheap.txt"

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            domains = [d.strip() for d in content.replace(",", "\n").splitlines() if d.strip()]

        # 清空输出文件
        open(output_file, "w").close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(lambda domain: process_domain(domain, output_file), domains)

        print(f"✅ 可注册域名已实时保存至 {output_file}")
    except FileNotFoundError:
        print("❌ 未找到 schools.txt 文件，请检查文件路径。")

if __name__ == "__main__":
    main()