# NAStool Agent 指南

本文件面向在本仓库工作的 Codex/代理。修改前先阅读 `docs/architecture.md`，并优先使用 CodeGraph 查询结构、调用链和影响范围。

## 项目概览

NAStool 是 Python 3.10 + Flask 的 NAS 影视资源自动化工具，核心能力包括站点检索、RSS/豆瓣订阅、下载器集成、下载完成后的媒体识别整理、站点养护和消息通知。

关键入口：

- `run.py`：初始化数据库、配置、定时任务、目录监控和 Web 服务。
- `web/main.py`：Flask 页面路由和 Webhook。
- `web/apiv1.py`：`/api/v1/` REST API。
- `web/action.py`：Web/API 命令分发中心。
- `app/scheduler.py`：APScheduler 定时服务。
- `app/sync.py`：目录监控与全量同步。
- `app/filetransfer.py`：媒体识别、转移、重命名、刮削主链路。
- `app/searcher.py`、`app/subscribe.py`、`app/rss.py`：搜索、订阅、RSS。
- `app/indexer/`：内置、Jackett、Prowlarr 索引器。
- `app/downloader/`：下载器聚合层和各客户端。
- `app/media/`：媒体识别、TMDB、豆瓣、Bangumi、NFO/图片刮削。
- `app/db/`：SQLAlchemy 模型、主库、媒体缓存库、Alembic 入口。

## 查询顺序

1. 优先用 CodeGraph 查询架构、符号、调用链和改动影响范围。
2. CodeGraph 结果不足时，用 `rg` 和小范围文件读取补上下文。
3. Windows 下读取中文文件时显式 UTF-8，例如 `Get-Content -Encoding UTF8`。
4. 不要基于乱码输出修改中文文本。先修正编码链路。

当前仓库已执行过 `codegraph init`，生成了 `.codegraph/`。如果 CodeGraph 不可用，可重新运行：

```powershell
codegraph init
```

若初始化在引用解析阶段被 watchdog 中断，先尝试现有索引是否可查询；必要时再按 CodeGraph 工具提示处理。

## 开发原则

- 遵循现有单例和 `init_config()` 配置重载模式。
- 新增 Web/API 动作时，通常同时更新 `web/apiv1.py` 和 `WebAction._actions`。
- 新增下载器、索引器、媒体服务器或消息渠道时，沿用聚合层加 client 子类的策略式结构。
- 涉及配置项时，同步检查 `config/config.yaml`、`check_config.py`、`app/conf/` 和页面/API。
- 涉及数据库结构时，更新 `app/db/models.py` 并新增 `db_scripts/` Alembic 迁移。
- 涉及媒体识别时，优先补充 `tests/cases/meta_cases.py` 和 `tests/test_metainfo.py`。
- 涉及真实下载器、媒体库、文件移动、删种、rclone 或 minio 时，默认使用临时目录或 mock，避免触碰用户真实数据。

## 验证

基础测试：

```powershell
python -m tests.run
```

不要直接运行 `python tests/run.py`；当前 Windows 环境下该方式会因为导入路径缺少仓库根而失败。若 `python -m tests.run` 报缺少 `ruamel.yaml` 等依赖，先安装 `requirements.txt`。

本地启动：

```powershell
$env:NASTOOL_CONFIG="D:\path\to\config.yaml"
python run.py
```

注意：

- 完整运行需要有效 `NASTOOL_CONFIG`。
- TMDB、站点、下载器、消息渠道等链路依赖外部配置和网络。
- 启动本地服务前先检查是否已有同项目实例，避免重复启动监听器和后台线程。

## 高风险区域

- `app/filetransfer.py`：文件移动、删除、链接、远程同步。
- `app/downloader/downloader.py`：真实下载器任务创建、状态修改、删种。
- `app/scheduler.py`、`app/sync.py`：后台线程、定时任务和 watchdog observer。
- `web/action.py`：统一命令分发，影响大量 Web/API 调用。
- `app/media/meta/`：中文资源命名识别，回归风险高。
- `config.py`、`check_config.py`：配置加载、升级和保存。

## 文档

项目架构、业务流程和模块地图见：

- `docs/architecture.md`
