import subprocess
import ipaddress
import threading
import argparse
import time
import sys
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                            QLineEdit, QSpinBox, QProgressBar, QMessageBox,
                            QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QColor, QPalette, QBrush, QLinearGradient

default_scan_ip = '192.168.1.0/24'

def ping(ip):
    """
    对指定IP执行ping操作，如果能ping通则返回True，否则返回False
    """
    try:
        # 针对Windows系统的ping命令，使用-n参数指定发送次数，-w指定超时时间(毫秒)
        output = subprocess.run(
            ["ping", "-n", "1", "-w", "500", str(ip)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1
        )
        return output.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        print(f"Ping {ip} 时出错: {e}")
        return False

class ScanThread(QThread):
    """
    扫描线程，用于在后台执行网络扫描，避免阻塞GUI
    """
    # 自定义信号
    update_progress = pyqtSignal(int, int)  # 当前进度，总数
    update_ip_status = pyqtSignal(str, bool)  # IP地址，是否活跃
    scan_complete = pyqtSignal(list, float)  # 活跃IP列表，耗时

    def __init__(self, network, max_workers=50):
        super().__init__()
        self.network = network
        self.max_workers = max_workers
        self.is_running = True

    def run(self):
        try:
            network = ipaddress.ip_network(self.network)
            active_ips = []
            total_ips = network.num_addresses
            processed_ips = 0
            
            start_time = time.time()
            
            # 使用线程池加速扫描过程
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_ip = {executor.submit(ping, ip): str(ip) for ip in network.hosts()}
                
                # 处理结果，as_completed会按完成顺序返回future
                for future in as_completed(future_to_ip):
                    if not self.is_running:
                        break
                        
                    ip = future_to_ip[future]
                    is_active = future.result()
                    
                    if is_active:
                        active_ips.append(ip)
                    
                    # 发送信号更新UI
                    self.update_ip_status.emit(ip, is_active)
                    
                    processed_ips += 1
                    self.update_progress.emit(processed_ips, total_ips)
            
            # 确保进度条完成到100%
            if self.is_running:
                self.update_progress.emit(total_ips, total_ips)
                
            elapsed_time = time.time() - start_time
            self.scan_complete.emit(active_ips, elapsed_time)
            
        except Exception as e:
            print(f"扫描出错: {e}")

    def stop(self):
        self.is_running = False

class IPScannerGUI(QMainWindow):
    """
    IP扫描器的图形界面
    """
    def __init__(self):
        super().__init__()
        self.scan_thread = None
        self.ip_cells = {}  # 存储IP单元格的字典
        self.active_ips = []
        
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("IP网段扫描器")
        self.setMinimumSize(580, 700)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 控制面板
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        
        # 网段输入
        control_layout.addWidget(QLabel("网段:"))
        self.network_input = QLineEdit(default_scan_ip)
        control_layout.addWidget(self.network_input)
        
        # 线程数设置
        control_layout.addWidget(QLabel("线程数:"))
        self.workers_input = QSpinBox()
        self.workers_input.setRange(1, 200)
        self.workers_input.setValue(50)
        control_layout.addWidget(self.workers_input)
        
        # 扫描按钮
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.clicked.connect(self.start_scan)
        control_layout.addWidget(self.scan_button)
        
        # 停止按钮
        self.stop_button = QPushButton("停止扫描")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)
        
        main_layout.addWidget(control_panel)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v/%m)")  # 显示百分比和具体数值
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #BDBDBD;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        main_layout.addWidget(self.status_label)
        
        # IP表格
        self.ip_table = QTableWidget(16, 16)  # 16x16表格，共256个单元格
        self.ip_table.setEditTriggers(QTableWidget.NoEditTriggers)  # 禁止编辑
        self.ip_table.setSelectionMode(QTableWidget.NoSelection)  # 禁止选择
        self.ip_table.setShowGrid(True)  # 显示网格线
        self.ip_table.setGridStyle(Qt.SolidLine)  # 设置网格线样式为实线
        self.ip_table.horizontalHeader().setVisible(True)  # 显示水平表头
        self.ip_table.verticalHeader().setVisible(True)  # 显示垂直表头
        
        # 设置表格样式 - 只设置网格线和表头，不设置单元格背景色
        self.ip_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #424242;  /* 深灰色网格线 */
                background-color: white;
                border: 1px solid #BDBDBD;
            }
            QHeaderView::section {
                background-color: #E0E0E0;
                border: 1px solid #BDBDBD;
                padding: 2px;
            }
        """)
        
        # 设置表头
        for i in range(16):
            self.ip_table.setHorizontalHeaderItem(i, QTableWidgetItem(str(i)))
            self.ip_table.setVerticalHeaderItem(i, QTableWidgetItem(str(i * 16)))
        
        # 调整单元格大小
        self.ip_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.ip_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.ip_table.horizontalHeader().setDefaultSectionSize(32)
        self.ip_table.verticalHeader().setDefaultSectionSize(32)
        
        main_layout.addWidget(self.ip_table)
        
        # 图例
        legend_layout = QHBoxLayout()
        
        # 未扫描图例
        unscanned_sample = QLabel()
        unscanned_sample.setFixedSize(32, 32)
        unscanned_sample.setStyleSheet("""
            QLabel {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #D2D2D2, stop:0.5 #BDBDBD, stop:1 #A0A0A0);
                border: 1px solid #666666;
                border-radius: 2px;
                margin: 1px;
            }
        """)
        legend_layout.addWidget(unscanned_sample)
        legend_layout.addWidget(QLabel("未扫描"))
        
        legend_layout.addSpacing(32)
        
        # 活跃IP图例
        active_sample = QLabel()
        active_sample.setFixedSize(32, 32)
        active_sample.setStyleSheet("""
            QLabel {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF7043, stop:0.5 #F44336, stop:1 #D32F2F);
                border: 1px solid #666666;
                border-radius: 2px;
                margin: 1px;
            }
        """)
        legend_layout.addWidget(active_sample)
        legend_layout.addWidget(QLabel("活跃IP"))
        
        legend_layout.addSpacing(32)
        
        # 空闲IP图例
        inactive_sample = QLabel()
        inactive_sample.setFixedSize(32, 32)
        inactive_sample.setStyleSheet("""
            QLabel {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #9CCC65, stop:0.5 #8BC34A, stop:1 #689F38);
                border: 1px solid #666666;
                border-radius: 2px;
                margin: 1px;
            }
        """)
        legend_layout.addWidget(inactive_sample)
        legend_layout.addWidget(QLabel("空闲IP"))
        
        legend_layout.addStretch()
        
        main_layout.addLayout(legend_layout)
        
        self.show()
    
    def create_ip_grid(self, network):
        """
        创建IP地址表格
        """
        try:
            network = ipaddress.ip_network(network)
            base_ip = str(network.network_address).rsplit('.', 1)[0] + '.'
            
            # 清空IP单元格字典
            self.ip_cells = {}
            
            # 初始化表格，所有单元格设置为灰色（未扫描）
            for row in range(16):
                for col in range(16):
                    ip_last_octet = row * 16 + col
                    ip_str = f"{base_ip}{ip_last_octet}"
                    
                    # 创建空单元格
                    item = QTableWidgetItem()
                    item.setToolTip(ip_str)
                    item.setBackground(QBrush(QColor("#BDBDBD")))  # 灰色表示未扫描
                    
                    self.ip_table.setItem(row, col, item)
                    self.ip_cells[ip_str] = (row, col)
                    
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建IP表格时出错: {e}")
    
    def start_scan(self):
        """
        开始扫描网段
        """
        network = self.network_input.text().strip()
        workers = self.workers_input.value()
        
        try:
            # 验证网段格式
            ipaddress.ip_network(network)
            
            # 创建IP表格
            self.create_ip_grid(network)
            
            # 更新UI状态
            self.scan_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.progress_bar.setValue(0)
            self.status_label.setText(f"正在扫描网段 {network}...")
            
            # 创建并启动扫描线程
            self.scan_thread = ScanThread(network, workers)
            self.scan_thread.update_progress.connect(self.update_progress)
            self.scan_thread.update_ip_status.connect(self.update_ip_status)
            self.scan_thread.scan_complete.connect(self.scan_complete)
            self.scan_thread.start()
            
        except ValueError as e:
            QMessageBox.critical(self, "错误", f"无效的网段格式: {e}")
    
    def stop_scan(self):
        """
        停止扫描
        """
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.status_label.setText("正在停止扫描...")
            self.stop_button.setEnabled(False)
    
    def update_progress(self, current, total):
        """
        更新进度条
        """
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        
        if progress == 100:
            self.status_label.setText(f"扫描完成: {current}/{total} (100%)")
        else:
            self.status_label.setText(f"扫描进度: {current}/{total} ({progress}%)")
    
    def update_ip_status(self, ip, is_active):
        """
        更新IP状态
        """
        if ip in self.ip_cells:
            row, col = self.ip_cells[ip]
            item = self.ip_table.item(row, col)
            
            if is_active:
                # 活跃IP - 红色立体渐变效果
                gradient = QLinearGradient(0, 0, 0, 32)
                gradient.setColorAt(0, QColor(255, 112, 67))  # 亮红色
                gradient.setColorAt(0.5, QColor(244, 67, 54))  # 中红色
                gradient.setColorAt(1, QColor(211, 47, 47))  # 暗红色
                
                item.setBackground(QBrush(gradient))
                item.setData(Qt.UserRole, "active")
                self.active_ips.append(ip)
            else:
                # 空闲IP - 绿色立体渐变效果
                gradient = QLinearGradient(0, 0, 0, 32)
                gradient.setColorAt(0, QColor(156, 204, 101))  # 亮绿色
                gradient.setColorAt(0.5, QColor(139, 195, 74))  # 中绿色
                gradient.setColorAt(1, QColor(104, 159, 56))  # 暗绿色
                
                item.setBackground(QBrush(gradient))
                item.setData(Qt.UserRole, "inactive")
    
    def scan_complete(self, active_ips, elapsed_time):
        """
        扫描完成
        """
        self.active_ips = active_ips
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        # 确保进度条显示100%
        self.progress_bar.setValue(100)
        
        self.status_label.setText(f"扫描完成，发现 {len(active_ips)} 个活跃IP，耗时 {elapsed_time:.1f} 秒")
        
        # 显示结果统计
        message = f"扫描完成!\n\n发现 {len(active_ips)} 个活跃IP\n耗时: {elapsed_time:.1f} 秒"
        # QMessageBox.information(self, "扫描结果", message)

def scan_network(network, max_workers=50):
    """
    扫描指定网段中的所有IP，返回活跃的IP列表
    """
    network = ipaddress.ip_network(network)
    active_ips = []
    total_ips = network.num_addresses
    processed_ips = 0
    
    print(f"开始扫描网段 {network}，共 {total_ips} 个IP地址")
    start_time = time.time()
    
    # 使用线程池加速扫描过程
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for ip in network.hosts():
            futures.append(executor.submit(ping, ip))
        
        # 处理结果
        for i, future in enumerate(futures):
            ip = list(network.hosts())[i]
            if future.result():
                active_ips.append(str(ip))
                print(f"[+] 发现活跃IP: {ip}")
            
            processed_ips += 1
            if processed_ips % 10 == 0 or processed_ips == total_ips:
                progress = (processed_ips / total_ips) * 100
                elapsed = time.time() - start_time
                print(f"进度: {processed_ips}/{total_ips} ({progress:.1f}%) - 已用时间: {elapsed:.1f}秒", end="\r")
    
    print(f"\n扫描完成，共发现 {len(active_ips)} 个活跃IP，总耗时: {time.time() - start_time:.1f}秒")
    return active_ips

def main():
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 命令行模式
        parser = argparse.ArgumentParser(description="批量Ping网段工具")
        parser.add_argument("network", help="要扫描的网段，格式如: 192.168.1.0/24")
        parser.add_argument("-w", "--workers", type=int, default=50, help="并发线程数，默认为50")
        parser.add_argument("-o", "--output", help="将结果保存到指定文件")
        args = parser.parse_args()
        
        try:
            active_ips = scan_network(args.network, args.workers)
            
            if args.output:
                with open(args.output, "w") as f:
                    for ip in active_ips:
                        f.write(f"{ip}\n")
                print(f"结果已保存到 {args.output}")
                
            print("\n活跃IP列表:")
            for ip in active_ips:
                print(ip)
                
        except ValueError as e:
            print(f"错误: {e}")
        except KeyboardInterrupt:
            print("\n扫描被用户中断")
    else:
        # GUI模式
        app = QApplication(sys.argv)
        window = IPScannerGUI()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()