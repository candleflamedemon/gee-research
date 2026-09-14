# 科研分享版 Python 代码规范

在 Mode A（`FULL_RESEARCH`）、Mode C（`SHARE_CODE`）或 Mode E
（`EXECUTE_AND_SHARE_CODE`）需要生成科研分享版代码时读取本文件。分享版的目标是让
老师、同学、合作者、甲方或审稿人能够独立阅读、理解、修改和交流科研方法；它不是
本机环境快照，也不能替代本地长期复现包。

当 Mode A 同时生成两种交付物时，分享版与 `reproduce/main.py` 必须是两个用途明确的
文件；不得用同一个文件复制或改名后冒充两种交付。它们可以共享同一已验证算法来源。

## 交付原则

- 单文件优先，除非算法规模或用户现有项目结构确实需要模块化。
- 提供完整可运行的 Python 源码，不使用“此处省略”“沿用上文”等占位表达。
- 参数集中在文件开头、配置对象或清晰的命令行参数中；不要把日期、ROI、阈值和输出
  ID 散落在算法代码里。
- 包含完整 import、Earth Engine 初始化、数据检查、核心算法、结果检查、可选 Export、
  `main()` 入口和必要的控制台输出。
- 详细中文注释应解释科研原因、数据单位、QA/mask、日期边界、scale、projection、公式、
  阈值和结果含义。不要逐行翻译语法或用大量注释掩盖结构。
- 文件名使用可识别的研究对象、数据或方法和时期，例如
  `<study>_<method>_<period>_share.py`；不得使用 `test.py`、`new.py`、`final2.py`、
  `final_final.py` 等含义不明名称。

## 可移植性与安全

- 不写入个人用户名、本机绝对路径、Codex 临时目录、虚拟环境绝对路径或凭据路径。
- 不包含 OAuth token、credential 内容、Google 密码、Service Account 私钥或任何
  认证材料。初始化应使用用户运行环境中已有的合法授权。
- Project、Dataset、ROI、日期、算法和输出参数可以作为集中、可修改的非秘密配置。
- 代码不能因为便于展示而使用伪造数据、常量 `unmask`、擅自更换数据集或扩大日期。
- 分享代码中的破坏性操作必须删除或默认关闭。若任务包含 Export，提供清晰、显式的
  提交开关或入口；Asset 目标存在时默认停止，不删除、不覆盖。

## 科研完整性

分享版至少保留与任务相关的下列环节：

1. 检查 Earth Engine 初始化失败并提示用户本人运行合法认证命令；不要自动绕过认证。
2. 在 `median`、`mean`、`mosaic`、`qualityMosaic`、`first` 或 `toBands` 前验证
   ImageCollection 非空、时间范围正确且所需 band 存在。
3. 保留源 mask，并清楚记录 scale factor、offset、QA/cloud mask 与重采样选择。
4. 执行适合输出类型的数据质量检查，例如 min/max/mean、percentile、有效覆盖率、
   类别面积或混淆指标；不为形式计算没有科研意义的统计量。
5. 输出足够的复现信息：Project、Dataset、ROI、日期、影像数量、band、算法参数、
   scale/projection、输出位置和 Task 信息（如适用）。
6. A/C/E 的分享版必须包含完整交互式地图生成代码，优先 `geemap.foliumap` + Earth Engine
   Python API；地图包含底图、ROI边界、原始/参考影像、最终结果、适用的Coverage/Mask、
   Layer Control，以及连续色标或离散类别图例。默认写入 `preview/map.html`。
7. C 未实际执行时明确说明“运行代码后生成 map.html”，不生成伪造结果地图。
   geemap缺失时保留计算结果，先显示实际环境名称、解释器/环境目录和Python版本，询问
   是否允许在该环境添加geemap；明确同意之前不安装、不换环境、不自动静态回退。
   非交互执行没有许可时标记待确认；用户接受静态方式后才使用回退。详见preview-rules。
8. 分享文件不得依赖个人 Skill 的绝对路径。单文件中包含所需地图/静态回退函数，或在
   用户允许的模块结构中交付完整依赖模块，不留下只能在当前Codex中运行的import。
   具体规则读 `preview-rules.md`；显示参数不得修改结果或统计。

## 与实际执行逻辑的一致性

Mode A 和 E 中，最终实际运行并验证成功的实现是唯一科研真源。分享版可以整理注释、
排版、函数名和阅读顺序，但不得改变：

- Dataset、ROI、日期与过滤条件；
- QA、云掩膜、NoData 和有效像元定义；
- band、scale factor、offset、指数/模型公式、阈值、分类规则和随机种子；
- 合成、统计、scale、projection、region 和 Export 参数。

生成后逐项对照实际执行版本。发现差异时，修改分享版使其与已验证逻辑一致；不要重新
发明一个“更漂亮”的算法。Mode C 未实际执行时，以用户确认的科研规格为真源，并在
交付说明与代码头部明确标记未完成真实 GEE 数据验证。

## 验证与诚实标记

- 至少运行 Python 语法检查，并检查 import、参数引用和 `main()` 入口。
- 仅当确实连接 Earth Engine、访问真实输入并获得预期的服务端结果时，才标记为实际
  数据验证通过。
- 只做语法、mock 或轻量构图测试时，应写明：
  “该代码根据当前科研要求生成，本轮没有实际调用 Earth Engine 完成完整数据验证。”
- 报告依赖及其用途；不为一个简单脚本添加无关的工程框架或依赖。

## 保存位置

保存新增科研分享版 Python 前，读取并遵守 [artifact-saving-rules.md](artifact-saving-rules.md)：
在当前项目的 `任务成果/` 下创建本次专用、不可覆盖的版本目录，
以该版本目录作为成果根，再按需要放入 `deliverables/<task>/share/`。不得直接把新分享
代码或预览图写进旧成果目录，也不得覆盖同名历史版本。若用户明确要求原位修改一个已经存在的
项目代码文件，则适用该保存规则的原位修改例外；新增的分享副本仍进入新的
版本成果目录。
