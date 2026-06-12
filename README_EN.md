[中文](README.md) / [English](README_EN.md)

# BroadlinkAC-OpenWRT

> OpenWRT router plugin for fully automatic air conditioning control via Broadlink RM. Weather-aware, storm-protected, 24/7 unattended operation.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenWRT](https://img.shields.io/badge/OpenWRT-21%2B-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)]()

## ✨ Features

- 🎛️ **LuCI Control Panel** — Web UI for AC control, device config, log viewing
- 🌤️ **Dual Weather Source** — Baidu + QWeather, auto-fallback + stale-cache rescue
- 🌀 **Storm Auto-Protection** — Force-shutdown all ACs when storm < 100km
- ⏰ **Scheduling + Auto-Adjust** — Timed on/off + temperature-adaptive mode switching
- 🛡️ **procd Daemon** — Boot auto-start + crash recovery + graceful degradation
- 📥 **Log Download** — 14-day date grid + Markdown file download

![Control Panel](控制面板.png) ![Global Settings](全局设置.png)

## 🚀 Quick Start

### 1. Download & Install

Grab the latest `broadlinkac_3.1-1_aarch64_generic.ipk` and `install.sh` from [Releases](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/releases).

Upload both files to your router's `/tmp/` directory, then SSH in and run:

```bash
cd /tmp
bash install.sh
```

`install.sh` handles everything: system dependencies → IPK install → hvac_ir via pip.

### 2. Open LuCI Control Panel

Navigate to: `http://192.168.1.1/cgi-bin/luci/admin/services/broadlinkac`

### 3. Configure API Key

**Services → Broadlink AC Control → Settings**:

| Source | Free Quota | Sign Up |
|--------|-----------|---------|
| Baidu Weather (recommended) | 150K calls/month | [Baidu Maps Console](https://lbsyun.baidu.com/apiconsole/key) |
| QWeather (fallback) | 50K calls/month | [QWeather Console](https://console.qweather.com) |

### 4. Scan for Devices

Click **Scan LAN Devices** in the control panel to auto-discover Broadlink RM.

## 🛠️ Compatibility

| Item | Supported |
|------|-----------|
| OpenWRT | 21.02+ |
| Python | 3.8+ |
| LuCI | 19.07+ |
| Broadlink Devices | RM Mini 3 / RM4 Mini / RM Pro+ |
| Architecture | aarch64_generic (A53/A55/A57/A72/A73/A76) |

## 📦 Manual IPK Build

```bash
cd ipk-build
python3 build_ipk.py
# Output: broadlinkac_3.1-1_aarch64_generic.ipk
```

## 📁 Directory Structure

```
broadlinkac/
├── files/
│   ├── etc/
│   │   ├── config/broadlinkac          # UCI default config
│   │   ├── init.d/broadlinkac          # procd daemon
│   │   └── uci-defaults/99-broadlinkac # First-boot setup
│   └── usr/
│       ├── lib/broadlinkac/            # Python core
│       │   ├── broadlinkac_core/       # Control / Weather / Storm / Scheduler / Log
│       │   ├── protocols/              # Custom IR protocols
│       │   ├── broadlinkac_api.py      # LuCI CLI interface
│       │   └── broadlinkac_service.py  # procd background daemon
│       └── lib/lua/luci/               # LuCI pages
│           ├── controller/broadlinkac.lua
│           ├── model/cbi/broadlinkac.lua
│           └── view/broadlinkac/dashboard.htm
├── ipk-build/                          # IPK build scripts
│   ├── build_ipk.py
│   └── CONTROL/{control,postinst}
└── install.sh                          # One-click installer
```

## 🔗 Sister Project

**[BroadlinkAC-For-Agent](https://github.com/oywq00008-cell/BroadlinkAC-For-Agent)** — Cross-platform desktop GUI + AI Agent interface (Windows / macOS / Linux).

Both projects share core algorithms, evolving independently:
- Desktop: interactive UI + rich user controls
- Router: 24/7 unattended + automatic response

## 📝 License

MIT — see [LICENSE](LICENSE)

## 🙏 Acknowledgments

- IR protocols: [python-broadlink](https://github.com/mjg59/python-broadlink) + [hvac_ir](https://github.com/nicko858/hvac_ir)
- Weather data: Baidu Maps Open Platform + QWeather
- Storm data: China NMC + US NHC
