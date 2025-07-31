import whois
import socket
import requests
import concurrent.futures
import threading

lock = threading.Lock()  # 确保多线程写入时不会冲突


def extract_main_domain(domain):
    """ 只获取主域名，例如 aluno.barrosmelo.edu.br -> barrosmelo.edu.br """
    parts = domain.split(".")
    if len(parts) > 3 and parts[-2] == "edu" and parts[-1] == "br":
        return ".".join(parts[-3:])  # 提取 edu.br 之前的部分
    return ".".join(parts[-2:])  # 默认返回主域名


def check_domain_availability(domain):
    """ 只对主域名进行 whois 查询，避免误判子域名 """
    main_domain = extract_main_domain(domain)

    try:
        socket.gethostbyname(main_domain)
        return False  # 解析成功，说明主域名已注册
    except socket.gaierror:
        pass  # DNS 查询失败，继续使用 whois 检查

    try:
        domain_info = whois.whois(main_domain)
        whois_text = str(domain_info).lower()

        if any(keyword in whois_text for keyword in ["no match for", "not found", "available"]):
            return True  # 确认可注册
        return False
    except Exception as e:
        error_message = str(e).lower()
        if "no match for" in error_message or "not found" in error_message or "available" in error_message:
            return True  # 解析异常信息，发现是“未找到域名”，判定为可注册
        print(f"⚠️ whois 查询 {domain} 失败: {e}")
        return None  # 无法确定状态


def check_website_accessibility(domain):
    """ 访问域名，查看是否有有效的网站 """
    url = f"http://{domain}"
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200  # 该域名可访问，可能仍在使用
    except requests.RequestException:
        return False  # 无法访问，可能真的是未注册的域名


def process_domain(domain, output_file):
    is_available = check_domain_availability(domain)
    if is_available:
        is_accessible = check_website_accessibility(domain)
        print(f"域名 {domain} 可注册: {is_available}, 可访问: {is_accessible}")
        if not is_accessible:
            with lock, open(output_file, "a", encoding="utf-8") as out_file:  # 立即保存
                out_file.write(domain + "\n")
    else:
        print(f"域名 {domain} 已注册")


def main():
    file_path = "domain.txt"
    output_file = "available_domains.txt"

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            domains = [d.strip() for d in content.replace(",", "\n").splitlines() if d.strip()]

        # 先清空文件，确保不会追加旧数据
        open(output_file, "w").close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(lambda domain: process_domain(domain, output_file), domains)

        print(f"✅ 可注册且无法访问的域名已实时保存至 {output_file}")
    except FileNotFoundError:
        print("❌ 未找到 schools.txt 文件，请检查文件路径。")


if __name__ == "__main__":
    main()
