# 本地长期科研复现规范

在 Mode A（`FULL_RESEARCH`）或 Mode D（`LOCAL_REPRODUCIBLE`）需要生成本地复现包
时读取本文件。目标不是展示代码，而是让用户在结束对话、关闭 Codex，甚至数月后仍能
在合法授权的本机环境中重新执行同一科研流程。

本地复现代码与科研分享版是不同交付物。`reproduce/main.py` 重视真实运行参数、环境、
日志和入口；分享版重视阅读与交流。不得把同一个文件简单复制或改名来代替二者，但二者
必须从同一最终科研逻辑派生。

## 成果根目录与不可覆盖规则

1. 保存新增本地复现 Python、参数、启动文件或代码包前，读取并遵守
   [artifact-saving-rules.md](artifact-saving-rules.md)。在当前项目的 `任务成果/` 下为本轮创建新的、不可
   覆盖的版本目录，并把该目录作为成果根；不要复用、清空或覆盖历史版本。
2. 在成果根中使用 `deliverables/<task-name>/`，按模式创建 `share/` 和/或
   `reproduce/`。已有 `outputs/`、`results/`、`experiments/` 等成熟结构可作为该版本
   目录内的组织参考，但不能绕过不可覆盖的版本目录规则。
3. 用户明确要求原位修改已有科研代码时，适用该保存规则的原位修改例外并
   保持原路径；新增的独立复现包、分享件和报告仍必须进入新的版本成果目录。

任务目录应使用研究对象、方法和时期等稳定含义，例如 `yushu_mrc_2023`。不得使用
`new`、`test`、`final2` 或 `final_final` 作为正式交付名称。

## 最小目录

根据任务实际需要生成文件，不创建空目录或空模板。复现包原则上至少包含：

```text
reproduce/
|-- main.py
|-- config.yaml                 # 或等价的参数文件
|-- requirements.txt
|-- README_REPRODUCE.md
`-- manifest.json
```

在 Mode A 且条件允许时，还应生成：

```text
reproduce/
|-- requirements-lock.txt       # 仅关键依赖的精确版本
|-- run.ps1                     # Windows 优先
|-- run.sh                      # 成本很低时提供
|-- logs/                       # 实际运行时保存精简日志
|-- preview/                    # 执行后生成 map.html，静态回退也存放于此
`-- metadata/                   # 仅有独立元数据文件时创建
```

## `main.py`

- 保存当前任务最终采用的计算逻辑，不保留失败实验、临时测试、废弃阈值或旧算法。
- 支持 `python main.py` 或 `python main.py --config config.yaml`；使用 `main()` 和标准
  `if __name__ == "__main__":` 入口。
- 通过 `Path(__file__).resolve().parent` 定位 config、日志和相对输入，不写个人绝对路径。
- 初始化 Earth Engine 时使用配置中的 Project 和操作系统已有授权。认证失败应明确提示
  用户本人运行 `earthengine authenticate`，然后退出；默认不强制打开浏览器。
- 每次重跑仍检查 ROI Asset、ImageCollection 是否为空、image count、所需 band、日期、
  数据类型和适用的数据质量/空间覆盖指标。不能因过去成功就省略输入检查。
- 若包含 Export，提交必须是显式参数或命令行开关；目标 Asset 已存在时默认报告冲突并
  停止，绝不删除、覆盖或替换历史成果。
- A/D 的 main.py 必须具备交互地图重新生成能力：计算和质量检查成功后自动调用
  geemap + Earth Engine Python API，写入当前运行成果根的 `preview/map.html`。
  地图函数和所需回退函数应随包完整交付，不能依赖个人Skill安装路径。每次运行使用新的
  不可覆盖运行成果目录（依 `artifact-saving-rules.md`），不得覆盖旧地图。
  独立运行时将同样的版本目录命名与冲突递增规则实现为Python/启动脚本逻辑，不依赖
  Codex仍在运行或能够调用Skill；README说明本轮地图的实际运行输出位置。

## 参数文件

将容易变化且具有明确科研含义的参数与代码分离，例如：

```yaml
project_id: example-project
roi_asset: projects/example-project/assets/study/roi
dataset_id: COPERNICUS/S2_SR_HARMONIZED
start_date: 2023-05-20
end_date: 2023-05-30
algorithm:
  index: NDVI
export:
  enabled: false
  scale: 10
  asset_id: projects/example-project/assets/results/example_ndvi
```

字段必须根据任务动态确定。日期、ROI 或输出位置的常见调整应优先改 config，而不是算法
源码；但不要为了两个简单参数引入过度复杂的配置系统。使用 YAML 时把 `PyYAML` 加入
依赖；也可选择不需要额外解析库的等价参数格式。

## 依赖与环境快照

`requirements.txt` 记录最小直接依赖：`earthengine-api`、交互地图所需的 `geemap`，以及
实际使用 YAML 时的 `PyYAML`。只有实际使用时才加入其他科研库。geemap缺失不应使
核心算法失败：保留结果，地图阶段先显示实际执行环境名称、解释器、环境目录、Python
版本及缺依赖情况，询问是否允许在该环境添加geemap。明确许可后才安装；不得自动更换/
创建环境。非交互运行没有答复时不安装，标记待确认。用户拒绝或安装失败时说明情况，
仅在用户接受后生成静态回退；保留安装后重跑生成HTML的入口。

`requirements-lock.txt` 保存实际验证环境中与任务有关的精确版本，如
`earthengine-api==...`、`google-api-python-client==...`、`PyYAML==...`。不要机械复制
整个 `pip freeze`，也不要记录 editable 私有路径、本机包路径、credential 或 token。

元数据至少记录：Python 版本、OS、earthengine-api 版本、Project ID、Dataset ID、ROI
Asset、时间范围、关键算法参数、输出参数和生成时间。实际执行时再记录 image count、
band、scale、适用的 projection/coverage、Task ID、Task description 和初始 state。
允许记录 OS 类型和版本，但不得记录用户名或个人目录。

config/manifest记录交互地图的参考与结果band、ROI、min/max、palette、离散类别图例、
适用的Coverage/Mask定义、`preview/map.html`相对路径、哈希和生成状态。
预览参数仅控制显示；复现时重新运行数值和覆盖检查。README明确运行 main.py或启动脚本
后自动生成地图；HTML需要网络，Earth Engine临时图层失效时应重新运行刷新，不是永久
离线数据包。生成后直接打开HTML；无桌面的批处理环境允许关闭自动打开，但仍保存地图。

## `manifest.json`

manifest 是任务元数据摘要，不打开源代码也应能理解实验。按任务调整字段，至少覆盖：

```json
{
  "task_name": "...",
  "created_at": "...",
  "execution_verified": false,
  "project_id": "...",
  "dataset_id": "...",
  "roi_asset": "...",
  "start_date": "...",
  "end_date": "...",
  "python_version": "...",
  "earthengine_api_version": "...",
  "algorithm": "...",
  "parameters": {},
  "outputs": {},
  "export_tasks": [],
  "warnings": []
}
```

如果真实 Earth Engine 执行并验证成功，才可写 `execution_verified: true`。Export 记录
Task ID、Description、type、Asset ID/Drive 位置、初始 state 和创建时间；`READY` 或
`RUNNING` 不代表导出已经完成。

## `README_REPRODUCE.md`

README 面向数月后的用户本人，不能依赖聊天上下文。至少说明：

1. 任务目标、Dataset、ROI、时间和核心算法；
2. 如何创建并激活虚拟环境；
3. `pip install -r requirements.txt`；
4. 首次或认证失效时由用户本人执行 `earthengine authenticate`；
5. 当前 Project 及所需权限；
6. config 中可以修改和不可随意修改的参数；
7. `python main.py --config config.yaml` 或 `./run.ps1` 的执行方式；
8. 输出位置、Export 冲突行为和 Task 查询方法；
9. 常见问题：认证失效、Project 无权限、Asset 不存在、数据集/波段变化、空集合、导出
   目标已存在；
10. 最终代码生成日期、必要 Warning，以及基于既有代码时的来源和主要改动。

项目已经使用 Git 且能安全读取时，可记录当前 commit hash；不要强制建立 Git，也不要
伪造版本历史。

## 启动脚本与日志

Windows 优先提供简单可靠的 `run.ps1`。使用 `$PSScriptRoot` 定位文件，检查 Python 或
项目约定的相对虚拟环境，调用 `main.py --config config.yaml`，把输出追加到 `logs/` 中
带时间戳的新日志，并返回 Python 的退出状态。不要写死用户名、盘符、当前 Codex 目录、
credential 路径或 token。成本很低且依赖兼容时可提供同等的 `run.sh`。

实际执行日志至少保留任务开始时间、Project、Dataset、ROI、日期、image count、核心
参数、质量检查、Export Task ID、Warning/Error 和完成状态。对异常文本进行必要脱敏，
绝不记录 credential、token、密码或私钥。只保留最终运行记录和重要科研结论，不长期
保存 `debug1.py`、`test_fix.py` 等中间垃圾。

## 随机过程与本地数据

- 仅当算法确实含 Random Forest、随机采样、train/test split、bootstrap 或本地随机数
  时，设置明确的 `random_seed`，同时写入 config 和 manifest；无随机过程不要强行添加。
- 若依赖 CSV、GeoJSON、Shapefile、Excel 或模型参数文件，在 config 和 README 中记录
  文件名、预期相对位置、用途、必需字段和是否必须存在。不要无条件复制大型原始数据；
  不能随代码分发时，说明合法获取方式和放置位置。

## 唯一真源与一致性检查

Mode A 中，最终真实执行并验证成功的实现是唯一科研逻辑真源。`main.py` 应最大程度保留
该逻辑；分享版仅可为阅读重排。交付前逐项核对实际执行、分享版和复现版的 Dataset、
ROI、日期、云/QA mask、band、scale factor/offset、公式、阈值、分类/模型逻辑、随机
种子、mask、scale/projection、region 和 Export 参数。

分享版可改变注释、排版、函数名和阅读结构；复现版可增加 config、logging、CLI 和
manifest，但两者都不得改变核心算法。发现不一致时立即从已验证实现重新派生并修复。
Mode D 未实际运行时，在 manifest 和最终报告中保留 `execution_verified: false`，不能把
语法检查说成科研验证。

## 完成检查与报告

完成前确认最小文件均可读、入口和配置引用正确、依赖最小、JSON/YAML 可解析、Python
语法通过、启动命令使用相对路径、日志与 manifest 无秘密，并且历史成果未被覆盖。

Mode A 的最终报告分别列出：实际执行事实与数据质量；分享版路径及其来源；复现目录、
`main.py`、config、requirements、README、`run.ps1`、manifest 和日志；最后给出未来
重新执行的准确命令。没有实际执行或没有 Export 时，明确标记，不制造 Task 信息。
