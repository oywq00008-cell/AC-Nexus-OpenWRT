# AC-Nexus-OpenWRT 全量审计报告

**审计日期**: 2026-06-25 | **范围**: 全部 23 个源文件

---

## 🔴 临界问题 (13 + 1 = 14)

| 文件 | 行 | 问题 |
|------|-----|------|
| `broadlink.py` | 310 | 线程锁语法错误: `with self.lock and socket...` → 锁从未获取 |
| `acnexus_service.py` | 21 | `_cached_devices` 多线程无锁共享 |
| `acnexus_api.py` | 67-110 | 同一请求读 config.json 3 次（重复 I/O + 不一致） |
| `typhoon.py` | 343-425 | `ty_ac_off_sent` 返回值被所有调用者忽略，台风关机逻辑失效 |
| `weather.py` | 25 | SSL 证书验证禁用 |
| `typhoon.py` | 33 | SSL 证书验证禁用 |
| `xiaomi_control.py` | 52,203 | SSL 禁用 + Socket 泄漏 |
| `xiaomi_cloud.py` | 35,71 | SSL 禁用 + OAuth 凭证明文存 /tmp |
| `ac_control.py` | 22 | Socket 泄漏（_get_primary_ip） |
| `scheduler.py` | 34 | 死代码: `all(...) and not any(...)` 永假 |
| `model/cbi/acnexus.lua` | 13 | `io.popen` nil crash |
| `model/cbi/acnexus.lua` | 16 | 正则声称支持 settings 路径但实际不支持（第1捕获组为空→忽略整行） |
| `uci-defaults/99-acnexus` | 33 | sed 特殊字符注入（`&` `\` `/`） |
| `postinst` | 77 | 同上 sed 注入 |

## 🟠 高危问题 (27 + 5 = 32)

| 文件 | 行 | 问题 |
|------|-----|------|
| `acnexus_service.py` | 159-278 | 6 处 `except:pass` 无声吞错 |
| `acnexus_service.py` | 268 | TOCTOU: `os.path.exists` → 读写竞态 |
| `acnexus_service.py` | 272 | RESULT_FILE 非原子写入 |
| `acnexus_service.py` | 286 | 无界线程创建（MIPS 内存风险） |
| `acnexus_service.py` | 84,99 | `__import__` 动态模块任意导入 |
| `acnexus_api.py` | 81-264 | 7 处无声吞错 |
| `acnexus_api.py` | 271 | `init()` 重复调用 |
| `config.py` | 48,55 | `config` 为 None 时 AttributeError |
| `config.py` | 40 | `str.isascii()` Python 3.7+ 兼容性 |
| `ac_control.py` | 6 | 模块级 `import broadlink` 阻止无博联场景 |
| `ac_control.py` | 114,129 | 动态模块导入 |
| `ac_control.py` | 76,151 | `send_ac` 每次都扫描全网 |
| `scheduler.py` | 197 | `idle_seconds` 最长可睡 49 天 |
| `scheduler.py` | 66 | 天气 fetch 失败无声跳过 |
| `logger.py` | 20,69 | O(n) 内存读日志，MIPS OOM 风险 |
| `weather.py` | 40 | 无数组边界检查 |
| `weather.py` | 105,129 | HTTP 响应未 close |
| `weather.py` | 130 | 假设响应一定是 gzip |
| `typhoon.py` | 49 | 数组边界检查缺失 |
| `typhoon.py` | 64 | JSONP 解析脆弱（贪婪匹配） |
| `xiaomi_control.py` | 62 | MIoT 索引全量加载 OOM |
| `xiaomi_control.py` | 178 | Token 长度不合法静默降级 |
| `xiaomi_cloud.py` | 226 | 孤儿轮询进程 |
| `xiaomi_poller.py` | 9 | `time.sleep(0.5)` 不稳定 |
| `xiaomi_poller.py` | 56 | config.json 无锁写入 |
| `controller/acnexus.lua` | 75 | `uci_set` key 未过滤 |
| `model/cbi/acnexus.lua` | 70 | 设备节只支持单引号值 |
| `Makefile` | 35-58 | CGI 脚本未安装 |
| `99-acnexus` | 12-31 | 缺少 `enabled` 字段 |
| `weather.py` | 35 | 外部依赖 `wget` |

## 🟡 中危问题 (23 + 3 = 26)

主要: UCI 解析脆弱（split/in 匹配）、IP 解析脆弱、日志目录无限增长、RC4 实例化开销、生成低熵 User-Agent、锁粒度不一致、`write_cfg` 返回值不检查、正则字符类遗漏 `\`、acnexus.cgi `groups=None` 崩溃等。

## 🟢 低危问题 (18 + 5 = 23)

主要: `__all__` 缺失、重复 import、无注释边界、硬编码列索引、设备节遗留字段、版本号不一致(3.2 vs 5.0-beta2)等。

---

## Top 5 立即修复建议

1. **broadlink.py:310** — 锁语法 `with self.lock and socket` → `with self.lock: with socket`
2. **typhoon.py:343-425** — `ty_ac_off_sent` 状态持久化（模块级变量）
3. **acnexus_service.py:21** — `_cached_devices` 加 `threading.Lock()`
4. **weather.py:25** 等 4 处 — 启用 SSL 证书验证
5. **uci-defaults/postinst** — sed 替换改用 Python/printf 避免注入
