# BroadlinkAC — AI 智能空调控制器

> 把普通空调变成智能空调 —— 基于 OpenWRT + Broadlink RM 红外遥控器

---

## 功能

- 🎮 Web 控制面板：手机/电脑遥控空调，调温度、切换模式
- 🌤️ 自动调温：外面热自动开制冷，外面冷自动开制热
- 🌀 台风自动关：台风靠近自动关空调
- ⏰ 多场景定时模板：工作日一套、周末一套，自由切换
- 🏷️ 多设备管理：支持多台博联设备，自动去重，可自定义昵称
- 📊 环境监测：实时温度、湿度、天气状态、风暴距离
- 📋 操作日志：可下载到本地查看

---

## 硬件要求

| 物品 | 说明 |
|------|------|
| OpenWRT 路由器 | GL-MT6000 或其他支持 opkg 的路由器 |
| Broadlink RM 红外遥控器 | RM4 Mini / RM4 Pro / RM Mini 3 等 |

---

## 安装（3 步）

### 1. 下载

从 [GitHub Releases](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/releases) 下载 `BroadlinkAC-3.2.zip`，解压得到 `broadlinkac_3.2.run` 和 `使用说明.txt`。

### 2. 上传到路由器

打开终端（命令行），根据你的操作系统执行：

**macOS / Linux：**

```bash
scp broadlinkac_3.2.run root@你的路由器IP:/tmp/
```

**Windows：**

```powershell
scp broadlinkac_3.2.run root@你的路由器IP:/tmp/
```

> 输入路由器密码即可（密码不会显示，这是正常的）。
> 
> 如果你的路由器 IP 不知道，通常在路由器背面贴纸上，一般是 `192.168.1.1` 或 `192.168.8.1`。

### 3. 安装

上传完成后，继续在终端执行：

```bash
ssh root@你的路由器IP "bash /tmp/broadlinkac_3.2.run"
```

> 全自动安装，1-2 分钟完成。

### 4. 开始使用

浏览器打开 `http://你的路由器IP/cgi-bin/luci/admin/services/broadlinkac`

**首次使用需要：**
1. 去「设置」页填写和风天气 API Key（[免费申请教程](https://github.com/oywq00008-cell/BroadlinkAC-OpenWRT/blob/main/docs/使用指南.md#申请天气-api免费)）
2. 搜索选择你的城市位置
3. 点击「扫描设备」发现博联 RM
4. 在设备设置中选择你的空调品牌

---

## 支持的空调品牌

格力、美的、华凌、小米、海尔、海信、日立、大金、三菱、松下、富士通、奥克斯、巴鲁、开利、现代、Fuego

---

## 项目结构

```
├── broadlinkac/files/          # 插件源代码
│   ├── usr/lib/broadlinkac/    # Python 后端
│   ├── usr/lib/lua/luci/       # LuCI 界面
│   └── etc/                    # 配置文件
├── build_run.sh                # .run 安装包构建脚本
├── installer_template.sh        # 安装包模板
├── install_manual.sh           # 手动安装脚本（开发者用）
└── docs/                       # 文档
```

---

## 从源码安装（开发者）

```bash
bash install_manual.sh 你的路由器IP
```

---

> 📖 详细使用文档：[docs/使用指南.md](docs/使用指南.md)
>
> by 欧阳小白
