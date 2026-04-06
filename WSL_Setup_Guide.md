# 🚀 进策智算 · Windows (WSL2) 部署指南

本指南将帮助您在 Windows 电脑上安装 Linux 系统（WSL2），并运行“进策智算”量化内阁。

## 第一阶段：安装 WSL2 (Linux)

1. **以管理员身份运行 PowerShell** (在开始菜单搜 PowerShell，右键以管理员运行)。
2. **执行安装命令**：
   ```powershell
   wsl --install
   ```
   *如果之前没装过，这会安装默认的 Ubuntu。如果已经装过，跳过此步。*
3. **重启电脑**（非常重要）。
4. **设置账号**：重启后，Ubuntu 窗口会弹出，请按照提示输入您喜欢的用户名和密码。

---

## 第二阶段：配置 Linux 环境

打开刚刚装好的 Ubuntu 窗口，依次输入以下命令：

1. **更新系统**：
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
2. **安装 Python 3**：
   ```bash
   sudo apt install python3-pip python3-dev -y
   ```
3. **安装依赖 (国内镜像提速)**：
   将本项目文件夹复制到 Ubuntu 中（可以直接在 Windows 文件管理器访问 `\\wsl$\Ubuntu\home\你的用户名\`）。
   在 Ubuntu 终端进入项目目录后执行：
   ```bash
   pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

---

## 第三阶段：数据库配置 (MySQL)

如果您需要本地数据库：
1. **安装 MySQL**：
   ```bash
   sudo apt install mysql-server -y
   ```
2. **启动 MySQL**：
   ```bash
   sudo service mysql start
   ```

---

## 第四阶段：启动机器人

1. **启动后台决策引擎 (Dashboard)**：
   ```bash
   python3 server.py --host 0.0.0.0 --port 8000
   ```
2. **访问指挥部**：
   在 Windows 浏览器输入：`http://localhost:8000/modern`

---

## 🌟 进阶：如何同步代码？

您可以在 Windows 上使用 **VS Code**，并安装 **WSL 扩展**，这样您就可以直接在 Windows 的 VS Code 里修改这个 Linux 上的项目代码了。

祝您开盘大吉！
