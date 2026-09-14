# gee-research：GEE科研助理Skill

面向 Codex 的 Google Earth Engine 遥感科研 Skill。它不仅生成代码，还指导代理检查
环境与输入、实际调用 Earth Engine Python API、诊断错误、验证数据质量、按授权提交
Export，以及交付分享代码和长期本地复现包。

本项目为 `v0.1.0` 预发布版，持续验证跨平台和不同环境下的使用行为。
它不是独立运行的科研算法软件，也不会自动获得 Google 或 GitHub 权限。

## 主要能力

- Python/API/OAuth来源存在性、Project、服务器和公共数据访问诊断。
- Image、ImageCollection、FeatureCollection及Folder等Asset的有界元数据检查。
- 指定日期与ROI的集合数量、波段、时间和投影检查，空集合明确停止。
- 科研真实性、源mask、单位/scale factor、空间覆盖与结果统计规则。
- 只读batch task查询；Image/Table到Asset或Drive的Export辅助函数，默认不提交，
  Asset已存在时阻止，不删除、不覆盖。
- 所有工作模式具备 `geemap` 交互式HTML地图能力，默认 `preview/map.html`。
- 详细中文注释的完整分享版Python，以及代码、配置、依赖、入口、README、manifest
  和必要日志组成的本地复现包。
- 仓库内已包含版本化保存规则，不需要作者私有Skill。

## 安装Skill

把此仓库的完整内容安装为一个名为 `gee-research` 的个人Skill文件夹。
默认路径为 `~/.codex/skills/gee-research`；若已设置 `CODEX_HOME`，使用其
`skills/gee-research`。实际目录必须直接包含 `SKILL.md`，不要多嵌套一层仓库目录。

也可请求 Codex：“将 https://github.com/candleflamedemon/gee-research 安装为个人Skill”。
已有同名Skill时先备份并确认升级方式，不覆盖原有定制。重新启动Codex或新建对话后
检查Skill发现情况，并可用 `$gee-research` 显式调用。

## 科研Python环境

使用你为科研任务选定的Python环境。本发布包不携带任何本机虚拟环境或认证材料。
核心脚本使用Python标准库和 `earthengine-api`；地图额外需要 `geemap`。
PyYAML仅在选用YAML配置时需要，其余依赖由实际科研任务决定。

你本人同意安装后，在所选环境中运行：

```sh
python -m pip install earthengine-api geemap
```

首次或认证失效时，由用户本人完成 `earthengine authenticate`。
代理不得读取、展示或复制认证文件，也不自动打开OAuth流程。
初始化使用显式Project、当前项目根的 `.gee-project.json`、Earth Engine默认Project
的顺序；不能从ROI的Asset命名空间擅自切换计算Project。

```json
{"project": "your-google-cloud-project-id"}
```

该配置只保存Project选择，不随仓库提交个人配置。

## 五种工作模式

每个新的独立科研任务都先询问一次模式并等待选择，默认不等于自动执行。
同任务的Debug、日期调整和Export继承已选模式，不反复询问。
纯环境诊断、认证或独立Asset/Task元数据查询不启动科研模式问答。

| 模式 | 交付与地图 |
|---|---|
| A 默认 FULL_RESEARCH | 实际执行验证、真实结果地图、完整分享代码、本地复现包 |
| B EXECUTE | 实际执行验证和真实结果地图，不额外整理代码包 |
| C SHARE_CODE | 完整分享代码含地图生成逻辑；未执行时说明“运行代码后生成 map.html” |
| D LOCAL_REPRODUCIBLE | 可移动的本地复现包，重跑入口自动生成地图，诚实记录是否真实验证 |
| E EXECUTE_AND_SHARE_CODE | 实际执行、真实地图和基于已验证逻辑的分享代码，无完整复现包 |

地图至少包含底图、ROI边界、指定数据的原始/参考影像、真实结果、适用Coverage/Mask、
Layer Control；连续结果有色标，分类结果有离散图例。显示参数不修改数值计算。
缺少geemap时先展示真实环境并询问安装许可，不自动安装、换环境或转静态预览。
地图成功保存后尝试为用户打开；在线瓦片可能过期，未来需重跑刷新，不是永久离线数据。

## 调用示例

1. “使用 $gee-research，只诊断当前环境，不执行正式科研任务。”
2. “使用 $gee-research，检查 projects/your-project/assets/study/roi 的类型和数量，
   不完整下载FeatureCollection。”
3. “使用 $gee-research，对该ROI的Sentinel-2 SR Harmonized在指定日期内合成NDVI，
   保留真实mask，检查统计和有效覆盖，先不Export。”新科研任务先选择模式。

直接使用脚本时，在仓库目录运行：

```sh
python scripts/gee_doctor.py --no-initialize
python scripts/gee_doctor.py --project your-google-cloud-project-id
python scripts/gee_asset_info.py --asset-id projects/your-project/assets/study/roi --project your-google-cloud-project-id
python scripts/gee_collection_probe.py --dataset COPERNICUS/S2_SR_HARMONIZED --start-date 2023-05-20 --end-date 2023-05-30 --roi projects/your-project/assets/study/roi --project your-google-cloud-project-id
python scripts/gee_task_status.py --project your-google-cloud-project-id --limit 10
python scripts/gee_export_helpers.py --show-contract
python scripts/gee_map_preview.py --show-contract
```

日期筛选的结束日期为exclusive，必须按用户科研定义说明边界，不擅自扩大日期。
地图与Export helper由科研代码import并传入真实ee对象，CLI说明不代表提交或科研执行。
每个脚本均支持 `--help`。静态缩略图helper保留，但只有用户接受回退后才使用。

## 成果与本地复现

新增成果先进入项目 `任务成果/` 下独立不可覆盖版本目录，然后使用
`deliverables/<task>/share/`、`reproduce/`、`preview/map.html` 等任务内结构。
详细命名、冲突递增和原位修改例外见
[artifact-saving-rules.md](references/artifact-saving-rules.md)。
复现包至少有main.py、参数文件、最小requirements、README_REPRODUCE.md和manifest.json。
Windows优先提供run.ps1；实际执行版本是算法唯一真源，分享和本地版本必须一致。

以后按包内README创建环境、安装依赖、本人授权、检查Project/配置，然后运行：

```sh
python main.py --config config.yaml
```

入口重新检查输入、集合、质量及Export冲突，并自动重建地图；无新授权时不提交Export。
未进行真实计算的代码包必须保持 `execution_verified: false`。

## 验证和限制

```sh
python -B -m unittest discover -s tests -v
```

测试主要使用离线mock验证安全边界，不创建正式Asset、不提交Export、不代表科研结果
已经通过真实GEE验证。发布验证还检查脚本语法、帮助入口、reference链接和Skill
frontmatter。公开版地图后端加载器在导入期间进行可撤销的兼容处理，不修改第三方库，
不依赖作者本机补丁。当前已测试Python 3.12，其他环境仍需验证。

数据权限、服务器配额、数据产品和API版本会变化，既往成功不保证未来成功。
不得把NoData当观测、用常量补科研缺测、偷偷换卫星或扩大时间；不确定的波段/QA/
scale factor应核对当前官方Earth Engine文档。公开代码许可不授予任何遥感数据权限。

MIT许可证仅覆盖本仓库内容，第三方包和数据遵循各自许可证与使用条款。
