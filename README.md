[中文](README.md) / [English](README_EN.md)

# BroadlinkAC-OpenWRT

> OpenWRT 路由器端 Broadlink 全自动空调控制插件。自动获取天气数据，7×24小时无人值守管控空调。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenWRT](https://img.shields.io/badge/OpenWRT-21%2B-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)]()

## ✨ 特性

- 🎛️ **LuCI 控制面板** — Web 界面控制空调、配置设备、查看日志
- 🌤️ **天气双数据源** — 百度 + 和风，自动回退 + 旧值兜底
- 🌀 **风暴自动保护** — 距离 < 100km 强制关闭所有空调
- ⏰ **定时 + 自动调温** — 2h 自动根据室外温度调整 + 整点定时开关机
- 🛡️ **procd 守护** — 开机自启 + 异常降级 + 崩溃自动拉起
- 📥 **日志下载** — 14 天日期网格 + Markdown 文件下载

## 📸 截图

![控制面板](控制面板.png) ![全局设置](全局设置.png)

## 🚀 快速开始

### 1. 下载 IPK

从 [Releases](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/releases) 下载最新 `broadlinkac_3.1-1_aarch64_generic.ipk` 和 `install.sh`。

将两个文件传到路由器 `/tmp/` 目录下，SSH 登录路由器后执行：

```bash
cd /tmp
bash install.sh
```

`install.sh` 会帮你干三件事：装系统依赖 → 装 IPK → 装 hvac_ir。

### 2. 打开 LuCI 控制面板

浏览器访问路由器 LuCI 界面（默认 `http://192.168.1.1`），点 **服务 → Broadlink 空调控制**。

### 3. 配置 API Key

**服务 → Broadlink 空调控制 → 设置**：

| 来源 | 免费额度 | 申请地址 |
|------|---------|----------|
| 百度天气（推荐） | 150,000 次/月 | [百度地图控制台](https://lbsyun.baidu.com/apiconsole/key) |
| 和风天气（备选） | 50,000 次/月 | [和风天气控制台](https://console.qweather.com) |

### 4. 扫描设备

控制面板点 **扫描局域网设备** 自动发现 Broadlink RM。

## 🛠️ 兼容性

| 项目 | 支持 |
|------|------|
| OpenWRT | 21.02+ |
| Python | 3.8+ |
| LuCI | 19.07+ |
| Broadlink 设备 | RM Mini 3 / RM4 Mini / RM Pro+ |
| 架构 | aarch64_generic（A53/A55/A57/A72/A73/A76 等） |

## 📦 手动构建 IPK

```bash
cd ipk-build
python3 build_ipk.py
# 产物: broadlinkac_3.1-1_aarch64_generic.ipk
```

## 📁 目录结构

```
broadlinkac/
├── files/
│   ├── etc/
│   │   ├── config/broadlinkac          # UCI 默认配置
│   │   ├── init.d/broadlinkac          # procd 守护脚本
│   │   └── uci-defaults/99-broadlinkac # 首次安装初始化
│   └── usr/
│       ├── lib/broadlinkac/            # Python 核心
│       │   ├── broadlinkac_core/       # 控制/天气/台风/调度/日志
│       │   ├── protocols/              # 自研红外协议
│       │   ├── broadlinkac_api.py      # LuCI CLI 接口
│       │   └── broadlinkac_service.py  # procd 后台守护
│       └── lib/lua/luci/               # LuCI 页面
│           ├── controller/broadlinkac.lua
│           ├── model/cbi/broadlinkac.lua
│           └── view/broadlinkac/dashboard.htm
├── ipk-build/                          # IPK 打包脚本
│   ├── build_ipk.py
│   └── CONTROL/{control,postinst}
└── install.sh                          # 一键安装脚本
```

## 🔗 姊妹项目

**[BroadlinkAC-For-Agent](https://github.com/oywq00008-cell/BroadlinkAC-For-Agent)** — 跨平台桌面 GUI + AI Agent 接口（Windows / macOS / Linux）。

两个项目共享核心算法，独立进化：
- 桌面端：用户主动操作 + 丰富交互
- 路由器端：7×24 无人值守 + 自动响应

## 📝 License

MIT — 详见 [LICENSE](LICENSE)

## 🙏 致谢

- 红外协议基于 [python-broadlink](https://github.com/mjg59/python-broadlink)
- 天气数据来自百度地图开放平台 + 和风天气
- 风暴数据来自中国中央气象台 (NMC) + 美国国家飓风中心 (NHC)
