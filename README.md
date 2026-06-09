[-中文-](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/blob/main/README.md) / [-English-](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/blob/main/README_EN.md)
# BroadlinkAC-OpenWRT

> OpenWRT 路由器端Broadlink全自动空调控制插件，自动获取天气数据，实现路由器全天候自动管控空调和调温

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenWRT](https://img.shields.io/badge/OpenWRT-21%2B-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)]()

## ✨ 特性

- 🎛️ **LuCI 控制面板** — Web 界面控制空调、配置设备、查看日志
- 🌤️ **天气双数据源** — 百度 + 和风，自动回退 + 旧值兜底
- 🌀 **台风自动保护** — < 100km 强制关闭所有空调，防止外机损毁
- ⏰ **定时 + 自动调温** — 2h自动根据室外温度调整 + 整点定时按温度规则开关机
- 🛡️ **service 守护** — procd 守护 + 开机自启 + 异常降级
- 📥 **日志下载** — 14 天日期网格 + Markdown 文件下载
- 🔌 **UCI 双向同步** — CBI 设置 ↔ config.json 自动同步

## 📸 截图

![控制面板](控制面板.png) ![全局设置](全局设置.png)

## 🚀 快速开始

### 1. 下载 IPK

从 [Releases](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/releases) 下载最新 `.ipk`：

```bash
scp broadlinkac_3.0-1_*.ipk root@192.168.1.1:/tmp/
ssh root@192.168.1.1
opkg install /tmp/broadlinkac_3.0-1_*.ipk
```

### 2. 打开 LuCI 控制面板

- 浏览器访问：进入路由器的LuCI界面，点击“服务”下的Broadlink空调控制
- 正常默认是192.168.1.1或者192.168.0.1，请根据自己的路由器使用


### 3. 配置 API Key

**服务 → Broadlink 空调控制 → 设置**：
- 百度天气 API Key（[申请](https://lbsyun.baidu.com/apiconsole/key)）— 推荐
- 和风天气 API Key + Host（[申请](https://dev.qweather.com/)）— 备选
- 双天气源都是免费的，百度每月150000次调用，和风每月50000次调用

### 4. 扫描局域网设备

在控制面板点 `⚙️ 设备设置 → 🔄 扫描设备` 自动发现 Broadlink RM 设备。

## 🛠️ 兼容性

| 项目 | 支持版本 |
|------|----------|
| OpenWRT | 21.02+ |
| Python | 3.8+ |
| LuCI | 19.07+ |
| Broadlink 设备 | RM Mini 3 / RM4 Mini / RM Pro+ |
| 架构 | aarch64 / armv7 / x86_64 |

## 📦 手动构建 IPK

```bash
cd ipk-build
python3 build_ipk.py
# 产物: broadlinkac_3.0-1_<arch>.ipk
```

## 🔧 开发模式（推送代码到路由器调试）

```bash
# 编辑器改完代码后, 用 paramiko stdin 管道推送到路由器
python router_sync.py
```

> 注: OpenWrt dropbear 不支持 SFTP, 必须用 stdin 管道。

## 📁 目录结构

```
broadlinkac/
├── files/
│   ├── etc/
│   │   ├── config/broadlinkac          # UCI 默认配置
│   │   ├── init.d/broadlinkac          # procd 守护
│   │   └── uci-defaults/99-broadlinkac # 首次安装脚本
│   └── usr/
│       ├── lib/broadlinkac/            # Python 核心 + 协议
│       │   ├── broadlinkac_core/
│       │   │   ├── ac_control.py
│       │   │   ├── config.py
│       │   │   ├── logger.py
│       │   │   ├── scheduler.py
│       │   │   ├── typhoon.py
│       │   │   └── weather.py
│       │   ├── protocols/              # 自研红外协议
│       │   │   ├── haier.py
│       │   │   ├── aux_ac.py
│       │   │   └── panasonic.py
│       │   ├── broadlinkac_api.py      # LuCI 调用的 CLI
│       │   └── broadlinkac_service.py  # procd 后台守护
│       └── lib/lua/luci/               # LuCI 视图
│           ├── controller/broadlinkac.lua
│           ├── model/cbi/broadlinkac.lua
│           └── view/broadlinkac/dashboard.htm
├── Makefile                            # IPK 打包元数据
└── ipk-build/build_ipk.py              # 打包脚本
```

## 🔗 多平台桌面端和Agent调用的项目

**项目仓库**：[BroadlinkAC-For-Agent](https://github.com/oywq00008-cell/BroadlinkAC-For-Agent)
- 跨平台桌面 GUI（Windows / macOS / Linux）
- AI Agent Skill 接口
- 更多功能，更加灵活，强烈推荐！

**路由器端（本仓库）**：
- 7×24 小时无界面运行
- 天气/台风自动响应
- 自动化根据室外天气调整温度
- 适合"装了就不用管"的场景

两个项目**共享核心算法**（ac_control / typhoon / weather / scheduler），但**独立进化**——路由器端走"安全优先 + 兜底降级"，桌面端走"用户配置 + 弹窗交互"。

## 📝 License

MIT — 详见 [LICENSE](LICENSE)

## 🙏 致谢

- 红外协议基于 [python-broadlink](https://github.com/mjg59/python-broadlink) 二次开发
- 天气数据来自百度地图开放平台 + 和风天气(免费申请)
- 台风数据来自中国气象局 (NMC) / 美国国家飓风中心(NHC)
