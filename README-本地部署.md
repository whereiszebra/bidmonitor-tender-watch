# BidMonitor 部署与改造说明（跨平台）

本目录是 [zhiqianzheng/BidMonitor-AI](https://github.com/zhiqianzheng/BidMonitor-AI) 的本地部署，并针对
**「管式膜 / 智慧水务」**监控做了数据层改造，同时接入了**国际标讯源（欧盟 TED、联合国 UNGM）**。
原项目本身跑不出有效数据，改造原因见下文。

---

## 〇、在另一台机器上部署（最重要）

### 前置要求

- **Python 3.9+**（本机用的是 3.14，实测依赖全部兼容）
- **`curl`**（启动脚本用它做健康检查，非必需）
- 无需 Chrome / ChromeDriver —— 专用采集器都走 HTTP 接口，不用浏览器
  （原项目的 Selenium 模式只对那批已停用的国内站有用）

### 三步跑起来

```bash
git clone <仓库地址> && cd bidmonitor

bash setup.sh     # 建 venv + 装依赖 + 从模板生成配置
bash start.sh     # 启动，默认 http://127.0.0.1:8080
```

Windows 上推荐用 **Git Bash** 执行上面三条；PowerShell 的等价命令见下方「Windows 手动安装」。

### 关键说明：什么在仓库里，什么不在

| 内容 | 是否入库 | 说明 |
|---|---|---|
| `src/`、`server/app.py` 等代码 | ✅ | 全部采集器与业务逻辑 |
| `server/server_config.example.json` | ✅ | **配置模板**（已预置关键词/站点，无任何密钥） |
| `server/server_config.json` | ❌ 已忽略 | 本机运行配置；另一台机器由 `setup.sh` 从模板生成 |
| `server/data/bids.db` | ❌ 已忽略 | 数据由自己采集积累，仓库不带历史数据 |
| `.venv/`、`.selenium-cache/`、日志 | ❌ 已忽略 | 目标机器重建 |

所以新机器**不会**带着我这边的数据，第一次启动后需要自己跑一轮（浏览器点「立即检索」或 `POST /api/run-once`）。

### 可覆盖的环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `BIDMONITOR_PORT` | `8080` | 服务端口 |
| `BIDMONITOR_HOST` | `127.0.0.1` | 监听地址（要局域网访问用 `0.0.0.0`） |
| `BIDMONITOR_USER` | `CDKJ` | Web 登录账号 |
| `BIDMONITOR_PASSWORD` | `cdkj` | Web 登录密码 |

```bash
# 例：换端口 + 换密码 + 允许局域网访问
BIDMONITOR_PORT=9000 BIDMONITOR_PASSWORD='yourpass' BIDMONITOR_HOST=0.0.0.0 bash start.sh
```

> ⚠️ `BIDMONITOR_HOST=0.0.0.0` 会把带默认弱密码的面板暴露到局域网，务必同时改密码。

### Windows 手动安装（不用 Git Bash）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
copy server\server_config.example.json server\server_config.json
cd server
..\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8080
```

浏览器打开 http://127.0.0.1:8080 即可。

---

## 一、快速使用（本机）

```bash
cd bidmonitor
bash setup.sh                          # 首次：建 venv + 装依赖 + 生成配置
bash start.sh                          # 启动（默认 http://127.0.0.1:8080）
bash stop.sh                           # 停止
tail -f server/logs/server.log         # 看日志
```

- 访问地址：**http://127.0.0.1:8080**
- 账号 / 密码：**CDKJ / cdkj**（HTTP Basic；可用 `BIDMONITOR_USER`/`BIDMONITOR_PASSWORD` 覆盖，不必改源码）
- 当前监控间隔：**360 分钟**（6 小时）
- 数据落库：`server/data/bids.db`（SQLite）

> 注意：这是**前台进程式**部署，不是系统服务。机器重启或进程被杀后需要重新 `bash start.sh`。

---

## 二、为什么必须改造原项目

原项目（2025-12 生成，之后无维护）的采集层实测基本失效：

| 问题 | 实测证据 |
|---|---|
| 45 个站点里 44 个失败 | 只有 `chinabidding` 注册了专用爬虫，其余走"抓首页链接"的通用爬虫 |
| 12 个专用爬虫是**死代码** | `monitor_core.get_all_crawlers()` 原来只注册了 `chinabidding` 一个 |
| 多个源 URL 已失效 | `deal.ggzy.gov.cn/.../dealList_find.jsp` → 502；`china-tender.com.cn/search` → 404 |
| 多数站点在登录墙后 | 国家电网、华能、电建、隆基等 40 站的公告需登录才能看 |
| 唯一"成功"的数据是旧闻 | 59 条全部来自 `chinabidding`，内容是 **2023-11** 的链接与新闻稿，且无发布日期 |
| 桌面版不可用 | 依赖 Tkinter，本机 Homebrew Python 3.14 无 `_tkinter`，故只用 `server/` Web 版 |

---

## 三、做了什么改造

### 1. 重写 `src/crawler/ggzy.py`（核心）

原实现抓 `deal.ggzy.gov.cn` 的 JSP 接口（已失效）。实际数据来自**官方 AJAX 接口**：

```
POST https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList
Content-Type: application/x-www-form-urlencoded

FINDTXT     = 关键词
DEAL_TIME   = 时间范围代码（必填）
PAGENUMBER  = 页码
```

关键实测结论（都写进了代码注释）：

- **`DEAL_TIME` 必填**，缺参数直接报错；`01/02/03/06` 返回 0 条，**`04`/`05` 才返回真实数据**，默认用 `04`。
- **关键词无命中时会回退返回全量列表**：搜「管式膜」返回 `total=1000`，首条与不带关键词的列举完全相同。
  → 所以采集器只负责拉候选，**精确过滤交给 `KeywordMatcher` 在本地对标题做**。
- 接口有风控：`code=829` 要验证码、`800` 过于频繁、`804` 需细化条件 —— 命中即停止翻页，不硬刚。
- 返回字段规范：`title / publishTime / provinceText / cityText / businessTypeText / informationTypeText / url / id`，
  已拼进 `content` 便于人工核查。

### 2. 注册采集器

`src/monitor_core.py`：

- `get_all_crawlers()` 增加 `'ggzy': GGZYCrawler`（原来只注册了 `chinabidding`）。
- `get_default_sites()` 增加 `ggzy` 条目 —— **服务端是把 `enabled_sites` 与这张表求交集的**，
  注册表里加了但这里没加，依然不会加载。

### 3. 配置收敛

- 关键词：
  - 中文（GGZY 用）：`管式膜, 智慧水务, 膜生物反应器, 污水处理, 膜法水处理`
  - 英文（TED / UNGM 用）：`water treatment, wastewater, membrane bioreactor, membrane filtration, water supply, desalination, sewage treatment`
  - 说明：配置里的 `keywords` 由「关键词匹配器」对**标题+content 做 OR 匹配**，所以中英词混在一列即可；
    真正的分语言过滤在各采集器内部完成（见「语言路由」）。
- 启用站点：`ggzy` + `ted` + `ungm`（原项目的 44 个国内站已证明无效/登录墙，全部关闭减噪）
- 间隔：360 分钟

---

## 四、国际源接入

`管式膜 / 智慧水务` 在国内是 GGZY 一站覆盖；国外没有"全国统一入口"，实测能免密钥直接用的只有两个：

| 源 | 形式 | 实测要点 |
|---|---|---|
| **TED 欧盟官方标讯** | `POST https://api.ted.europa.eu/v3/notices/search`，JSON | 官方、**免密钥**，覆盖全欧盟政府采购。查询语法有几处坑（见下） |
| **UNGM 联合国全球市场** | `POST https://www.ungm.org/Public/Notice/Search`，返回 **HTML 片段** | 免登录，每页固定 15 条，`PageIndex` 翻页；`Description` 可做服务端关键词过滤 |

### TED 的坑（都已在 `ted.py` 注释里）

- **排序只能写在 query 字符串里**：`SORT BY publication-date DESC`。
  把 `sortBy` / `orderBy` / `sort` 当 JSON 字段传，接口直接 **400**（实测确认）。
  不排序时默认返回 2016 年的老数据，会误以为接口坏了。
- 日期过滤是 `PD>=20260801`（`YYYYMMDD`，无横线）。
- 多语言字段是 `{语言: [值]}` 字典，标题要取 `eng`。
- `scope: "ALL"` 全量归档 / `"ACTIVE"` 仅开放中公告。
- 公告页地址：`https://ted.europa.eu/en/notice/-/detail/<publication-number>`。

### 语言路由（重要）

`MonitorCore` 只把**前 3 个关键词**传给爬虫，而国内/国外关键词语言不同。
所以三个采集器各自做语言过滤：

- `ggzy` 只保留**中文**关键词（英文对国内站无意义），无中文则兜底 `水务`；
- `ted` / `ungm` 只保留**非中文**关键词（英文库搜中文=0 结果），兜底 `water treatment` / `water`。

### 试过但当前不可用的国际源

| 源 | 结果 |
|---|---|
| 世界银行 World Bank | 采购页 200，但**没有公开的采购公告 API**（`/api/v2/procurement*` 全 404） |
| 亚洲开发银行 ADB | `adb.org/projects/tenders` 返回 **403**（对我方出口 IP 封锁） |
| UNDP / UNOPS 等机构官网 | 多走各自门户，未逐一接入；UNGM 已覆盖联合国体系主入口 |

---

## 五、当前效果（已验证）

一轮检索约 90 秒，入库 **72 条**真实公告、**全部带发布日期**：

| 来源 | 条数 | 最新日期 | 样本 |
|---|---|---|---|
| 全国公共资源交易平台 | 56 | 2026-09-12 | 徐汇智慧水务平台运维、衡阳智慧水务二期中标、灵丘供水管网智慧水务采购 |
| TED 欧盟标讯 | 11 | 2026-09-14 | 德国饮用水厂建设、西班牙饮用水厂工程、挪威透析用水处理设备、丹麦净水厂、瑞士湖水厂 |
| UNGM 联合国采购 | 5 | 2026-09-15 | 阿富汗 Khan D 供水服务、黎巴嫩 UNIFIL 供水长期协议、钻井与供水系统改造 |

GGZY 关键词命中：`智慧水务 49`、`膜生物反应器 7`、`污水处理 4`；`管式膜`/`MBR`/`水厂` 当期 0 条
（冷门词，正是要靠定时监控去发现新增）。

国际侧采集日志（候选 → 关键词命中）：

```
[OK] ggzy: Found 56 items, 56 new matches
[OK] ted:  Found 100 items, 11 new matches
[OK] ungm: Found 30 items,  5 new matches
```

---

## 六、已知限制与待办

1. **通知未配置 → 目前不会主动告诉你**。
   配置里 `email_enabled`/`sms_enabled` 是开的，但邮箱列表为空、短信 AK/SK 为空、微信公众号（pushplus）`token` 为空、
   联系人为 0。因此每轮检索**只入库，不推送**。需要在 Web 界面「通知设置」里填至少一种渠道。
2. 旧数据已按授权清空（`DELETE /api/history`），当前库里只有 GGZY / TED / UNGM 三类真实数据。
   `chinabidding` 站点已停用（内容陈旧、多为导航文字）。
3. **TED 每关键词只取 1 页（50 条）**：`ted_max_pages` 可调，但它是公共公益 API，
   调大前请权衡；另有 `ted_since` 控制只取某日期之后的公告。
4. **UNGM 每页固定 15 条**（`PageSize` 不生效），靠 `PageIndex` 翻页；
   当前 `ungm_max_pages=2`，即每关键词最多 30 条。
5. GGZY 结果里偶有**同一标题重复**（该站对一条公告会按"招标公告/招标文件"等多条记录分别发布，
   URL 不同、ID 不同），不是抓取 bug；去重键是 URL，所以会分别入库。
6. **没有 License**（上游未声明），商用前建议先确认授权。
7. 三个源都是公开接口/页面，仍属反爬范围，**请勿提高频率**；当前 6 小时一轮是安全区间。

---

## 七、目录说明

```
bidmonitor/
├── start.sh / stop.sh          # 本地启停脚本（新增）
├── server/                     # FastAPI Web 版（本机使用这个）
│   ├── app.py                  # 路由与业务逻辑
│   ├── static/index.html       # Web 界面
│   ├── server_config.json      # 运行配置（含敏感信息，勿外传）
│   ├── data/bids.db            # SQLite 数据
│   └── logs/server.log         # 日志
├── src/
│   ├── monitor_core.py         # 调度与采集编排（已改：注册 ggzy / ted / ungm）
│   ├── crawler/ggzy.py         # 【重写】全国公共资源交易平台采集器
│   ├── crawler/ted.py          # 【新增】欧盟 TED 官方标讯采集器
│   ├── crawler/ungm.py         # 【新增】联合国 UNGM 标讯采集器
│   ├── matcher/keyword.py      # 关键词匹配（OR 组 + 排除词 + must_contain）
│   └── database/storage.py     # SQLite 存储，去重键 = URL 的 MD5
└── .venv/                      # 独立虚拟环境（Python 3.14，依赖已装齐）
```

---

## 八、故障排查

| 现象 | 处理 |
|---|---|
| 网页打不开 | `./start.sh`，然后 `tail -20 server/logs/server.log` |
| 检索报 0 条 | 看日志里 `[ggzy]` 的返回码；`800` 说明太频繁，等一会；`829` 表示要验证码，需降低频率 |
| 换了关键词不生效 | 关键词决定采集候选范围，改动后**无需重启**，下一轮自动生效 |
| 想看某条公告原文 | 结果里的 URL 指向 `ggzy.gov.cn/information/deal/html/...`，浏览器直接打开 |
