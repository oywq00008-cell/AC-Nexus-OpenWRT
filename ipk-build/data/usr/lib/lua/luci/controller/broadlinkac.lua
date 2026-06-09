module("luci.controller.broadlinkac", package.seeall)

function index()
    entry({"admin", "services", "broadlinkac"},
        alias("admin", "services", "broadlinkac", "dashboard"),
        _("Broadlink 空调控制"), 60).dependent = true

    entry({"admin", "services", "broadlinkac", "dashboard"},
        template("broadlinkac/dashboard"), _("控制面板"), 10)

    entry({"admin", "services", "broadlinkac", "settings"},
        cbi("broadlinkac"), _("设置"), 20)

    entry({"admin", "services", "broadlinkac", "api"},
        call("api")).dependent = true

    entry({"admin", "services", "broadlinkac", "log_download"},
        call("log_download")).dependent = true
end

function api()
    local cmd = luci.http.formvalue("cmd") or ""
    local script = "/usr/lib/broadlinkac/broadlinkac_api.py"
    local result = luci.sys.exec("/usr/bin/python3 " .. script .. " '" .. cmd .. "' 2>/dev/null")
    luci.http.prepare_content("application/json")
    luci.http.write(result)
end

function log_download()
    -- 日志下载单独走一个 endpoint，绕开 luci.sys.exec 的 4KB 截断
    local date_str = luci.http.formvalue("date") or ""
    -- 安全校验：YYYY-MM-DD
    if not string.match(date_str, "^%d%d%d%d%-%d%d%-%d%d$") then
        luci.http.status(400, "Bad Request")
        luci.http.prepare_content("text/plain; charset=utf-8")
        luci.http.write("非法日期格式")
        return
    end
    local f = io.open("/root/.ac_controller/logs/" .. date_str .. ".md", "r")
    if not f then
        luci.http.status(404, "Not Found")
        luci.http.prepare_content("text/plain; charset=utf-8")
        luci.http.write("日志不存在: " .. date_str)
        return
    end
    local content = f:read("*all")
    f:close()
    luci.http.header("Content-Type", "text/markdown; charset=utf-8")
    luci.http.header("Content-Disposition", 'attachment; filename="broadlinkac-' .. date_str .. '.md"')
    luci.http.write(content)
end
