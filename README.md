# bping

Windows 下的批量 Ping 网段工具，支持 GUI 表格矩阵显示与命令行模式。可快速扫描指定网段，展示 0–255 的 IP 占用状态：
- 灰色：未扫描
- 红色：活跃（占用）
- 绿色：空闲（未占用）

![](./img/screenshot.gif)

## 功能特性
- 多线程并发扫描（默认 50 线程，可调）
- GUI 视图使用矩阵显示IP占用
- 命令行模式支持输出结果到文件

## 环境要求
- 不依赖 Windows 系统 `ping` 命令
- Python 3.9+（推荐）
- 依赖：`PyQt5、pythonping`

## 安装依赖
```bash
pip install -r requirements.txt
```

## 运行（GUI）
```bash
python bping.py
```
- 默认网段：`192.168.1.0/24`
- 可在界面中设置网段与线程数，点击“开始扫描”

## 运行（命令行）
```bash
python bping.py 192.168.1.0/24 -w 100 -o result.txt
```
- `network` 网段（CIDR）：如 `192.168.1.0/24`
- `-w, --workers` 并发线程数（默认 50）
- `-o, --output` 将活跃 IP 保存到文件（可选）

