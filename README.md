**中文** / [English](README_EN.md)

# AC-Nexus-OpenWRT

> 专为 OpenWRT 路由器重写的 AC-Nexus 版本，拥有原版全部重要功能并保持极致轻量化，专为低性能路由器重新设计代码！全自动空调控制插件。支持博联 RM 红外遥控器和所有可接入米家 MIoT 生态的智能红外遥控器，自动获取天气数据，智能判断风暴风速和距离关闭空调，7×24 小时无人值守管控空调，自动根据室外温度开关机、自动调温。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenWRT](https://img.shields.io/badge/OpenWRT-21%2B-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)]()

## ✨ 特性

- 🎛️ **LuCI 控制面板** — Web 界面遥控空调、定时模板、温度规则、多设备管理
- 🌤️ **天气双数据源** — 百度 + 和风，自动回退，旧值兜底
- 🌀 **风暴三级自动保护** — 强台风100km / 台风70km / 默认50km 三级判定，自动关空调 + 暂停定时
- ⏰ **多日期组定时模板** — 工作日一套、周末一套，支持多时间段
- 🌡️ **独立温度规则** — 根据室外温度自动决策开机模式/温度
- 🏷️ **多品牌设备管理** — 博联 RM / 米家空调伴侣 / 米家红外遥控器，自动去重，自定义昵称
- 🔌 **小米 MIoT 全支持** — OAuth 扫码登录，自动拉取设备列表，按型号在线匹配 siid/piid，内置 3400+ 型号本地索引
- 🛡️ **内置核心库** — hvac_ir、broadlink、schedule、pyaes 全内置，零 pip 依赖
- 📥 **日志下载** — Markdown 格式按天存档，浏览器一键下载

## 📸 截图

| 控制面板 | 定时开关机 & 自动调温 |
|----------|----------------------|
| ![](assets/控制面板.PNG) | ![](assets/定时开关机%26自动调温.PNG) |

| CBI 设置 | 温度规则 |
|----------|----------|
| ![](assets/CBI设置.PNG) | ![](assets/温度规则.PNG) |

## 🚀 快速开始

> **前提：路由器已联网，存储空间 ≥ 15MB。**

### 方式一：IPK 安装（推荐 ⭐）

最简单、最适合新手。从 [Releases](https://github.com/oywq00008-cell/AC-Nexus-OpenWRT/releases) 下载 `acnexus_*.ipk`：

1. 浏览器打开路由器 LuCI 后台
2. **系统 → 软件包 → 上传软件包**
3. 选择下载的 `.ipk` 文件
4. 等待安装完成（会看到 6 步进度提示），刷新页面即可使用

> IPK 安装时会自动完成：CRLF 修复、权限设置、Python 模块验证、config.json 生成、LuCI 缓存刷新、服务启动。**全程无需手动干预。**

### 从旧版 BroadlinkAC 升级

从旧版升级前，先在路由器上执行清理脚本：

```bash
scp cleanup_old_broadlinkac.sh root@你的路由器IP:/tmp/
ssh root@你的路由器IP "bash /tmp/cleanup_old_broadlinkac.sh"
```

然后再用方式一或方式二安装新版。

### 开始使用

浏览器打开 `http://你的路由器IP/cgi-bin/luci/admin/services/acnexus`

**首次使用需要：**
1. 去「设置」页填写和风天气 API Key（[免费申请教程](https://github.com/oywq00008-cell/AC-Nexus-OpenWRT/blob/main/docs/使用指南.md#申请天气-api免费)）
2. 搜索选择你的城市位置
3. 点击「扫描设备」发现博联 RM
4. 在设备设置中选择你的空调品牌

## 🎛️ 支持的空调品牌

博联红外协议（17 品牌）：格力、美的、华凌、小米、海尔、海信、日立、大金、三菱、松下、富士通、奥克斯、巴鲁、开利、现代、Fuego、AUX 奥克斯

> 💡 **米家红外遥控器用户**：直接接入米家的红外遥控器自带官方海量码库，在米家 App 中绑定空调即可，插件通过 MIoT 协议控制，不受上述品牌列表限制。

## 📂 项目结构

```
├── acnexus/files/              # 插件源代码
│   ├── etc/
│   │   ├── config/acnexus      # UCI 配置模板
│   │   ├── init.d/acnexus      # 服务管理脚本
│   │   └── uci-defaults/       # 首次安装 config 生成
│   ├── usr/lib/acnexus/        # Python 后端
│   │   ├── acnexus_core/       # 核心逻辑（config/scheduler/weather/typhoon/ac_control）
│   │   ├── hvac_ir/            # 13 种红外协议（内置）
│   │   ├── protocols/          # 自定义协议 + MIoT spec 索引
│   │   ├── broadlink/          # Broadlink SDK
│   │   ├── schedule/           # 定时任务引擎
│   │   └── pyaes/              # 纯 Python AES
│   └── usr/lib/lua/luci/       # LuCI 界面（controller/cbi/view）
├── ipk-build/                  # IPK 构建工具
│   ├── CONTROL/                # 安装控制文件
│   └── build_ipk.py            # 构建脚本
├── cleanup_old_broadlinkac.sh  # 旧版清理脚本
└── docs/                       # 文档
```

## 🔗 姊妹项目

**[AC-Nexus](https://github.com/oywq00008-cell/AC-Nexus)** — 跨平台桌面 GUI + AI Agent 接口（Windows / macOS / Linux）。

两个项目共享核心算法，独立进化：
- 桌面端：用户主动操作 + 丰富交互
- 路由器端：7×24 无人值守 + 自动响应

## ⚙️ 依赖说明

IPK 安装时 postinst 会自动处理以下依赖（无需手动操作）：

| 包名 | 用途 |
|------|------|
| `python3-codecs` | Unicode 支持（米家 MIoT HTTPS 通信必需） |

以下库已内置在插件中，不需要额外安装：

| 库 | 用途 |
|----|------|
| `broadlink` | 局域网发现/通信博联设备 |
| `hvac_ir` | 红外编码生成（13 品牌） |
| `schedule` | 定时任务引擎 |
| `pyaes` | 纯 Python AES 加密 |
| `_RC4` | 纯 Python ARC4（小米 MIoT 协议） |

## 📝 License

MIT — 详见 [LICENSE](LICENSE)

## 🙏 致谢

- 红外协议基于 [python-broadlink](https://github.com/mjg59/python-broadlink) 和 [hvac_ir](https://github.com/shprota/hvac_ir)
- 天气数据来自百度地图开放平台 + 和风天气
- 风暴数据来自中国中央气象台 (NMC) + 美国国家飓风中心 (NHC)
