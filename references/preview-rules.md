# 所有工作模式的交互式地图预览

本规则取代此前“静态缩略图为主、按需生成”的预览设计。A/B/C/D/E都必须具备交互式
地图预览能力，统一优先使用 `geemap` + Earth Engine Python API；用于HTML时推荐
通过 `load_folium_backend()` 加载Folium后端。静态helper保留为缺依赖/地图失败时的回退，不是替代目标。

## 各模式行为

- A：实际计算与质量检查成功后，基于同一真实服务端对象生成地图；保存分享代码和能自动
  重建地图的复现包。当前地图保存到 `deliverables/<task_name>/preview/map.html`。
- B：计算成功后必须生成真实结果地图，但不额外整理分享代码或完整复现包。
- C：分享版Python必须有完整地图代码；未执行时明确“运行代码后生成 map.html”，不得
  用模拟像元或空壳图冒充真实结果。只做语法检查不代表地图已生成。
- D：复现包的main.py/启动脚本计算成功后自动生成 `preview/map.html`；未实际执行则
  manifest仍为 execution_verified:false。
- E：实际生成真实结果地图；分享版保留完整地图生成逻辑，无完整复现包。

模式不改变算法。纯认证、环境、Task状态或Asset元数据查询没有科研结果时，不为满足
图层清单发明影像；能力保留，但地图生成标记不适用。

## 必需图层与显示

地图至少包含：底图、透明填充的ROI边界、指定时段内的原始/参考遥感影像、最终科研
结果、适用的Coverage/Mask层、Layer Control。参考影像需明确Dataset、日期和处理方法，
不得偷偷更换数据或扩大时间。优先直接把同一执行逻辑产生的参考/结果ee.Image传给地图。

连续结果使用合理连续palette和色标，记录bands/min/max；percentile拉伸应说明数值。
分类结果使用类别值—标签—颜色映射和离散图例。非连续类别码可只对显示副本remap为
连续索引，禁止修改真正的分类结果。Mask层应说明代表有效观测、云掩膜或覆盖次数等哪种
指标，不能把几何footprint当作云下有效覆盖。底图、ROI、图例和显示层不回写科研结果。

## 保存、打开与复现

- 默认相对路径 `preview/map.html`。A当前交付位于
  `deliverables/<task_name>/preview/map.html`；A/D复现运行在该轮运行成果根中生成
  `preview/map.html`。B/E也保存真实生成的HTML，不因没有复现包而省略。
- 所有新增HTML、PNG、代码与报告都按 [artifact-saving-rules.md](artifact-saving-rules.md) 创建新版本成果目录，
  上述路径均在该版本目录内；同名已有文件默认停止，不覆盖历史科研成果。
- 分享版和本地包必须自包含完整地图函数；不得引用个人Skill绝对路径。main.py和启动
  脚本自动调用地图生成，显示参数独立放入config，依赖记录geemap及实际验证版本。
  本机独立重跑需在代码中实现同样的版本目录分配规则，不依赖Codex对话或Skill工具。
- 成功生成后立即为用户打开本地HTML（Codex browser/panel或系统浏览器，受权限限制则
  请求必要授权并给出文件链接）。不能仅提供路径而不尝试打开。无桌面批处理可关闭打开。
- HTML引用在线底图和Earth Engine渲染瓦片，不是永久离线成果；瓦片访问可能过期，
  以后重跑科研/地图代码刷新。记录相对路径、生成状态、显示参数与哈希，不记录OAuth
  credential/token、密码、私钥或认证文件内容；不主动读取凭据。私有数据地图不得擅自发布。

## geemap不可用：先说明环境，再询问安装许可

核心计算结果不得因此失败或回滚，但地图阶段暂停等待用户决定，不能直接省略地图或
自动转静态预览。先只读检查实际执行科研代码的环境，不以Codex自带解释器代替：
环境名称/类型、`sys.executable`、`sys.prefix`、Python版本、geemap缺失或导入失败原因。
这些路径为本轮动态诊断信息，不得硬编码进分享代码或复现包。

向用户显示真实信息并询问，例如：

> 当前科研代码使用环境：<实际环境名称/类型>；Python版本：<实际版本>。\
> 解释器：<实际sys.executable>\
> 环境目录：<实际sys.prefix>\
> 当前无法导入geemap。安装将向上述环境添加geemap及依赖，可能调整相关依赖版本。\
> 是否允许在这个环境中安装geemap？我会等待你的明确回复，不会自动安装或换环境。

- 用户明确同意后，使用该解释器的 `-m pip install geemap`（或该环境明确使用的包管理
  方式），遵守系统权限审批；不使用不确定归属的裸pip，不添加未经许可的升级/重建操作。
- 安装后检查该解释器能import geemap及版本，再重试地图。工作模式A等的选择不等于
  安装许可，编写requirements也不等于已授权自动安装。
- 用户拒绝、暂不安装或安装失败时，报告地图未生成及原因，提供静态预览选项；不得未经
  用户同意自动切换预览方式、换环境或创建环境。保留原来的静态helper与地图代码。
- 独立分享/复现程序同样先显示动态环境信息并征求许可；非交互运行无有效答复时不安装，
  返回待确认状态，保留核心计算结果。不能依赖Codex正在运行才能安全处理缺依赖。
- helper返回 `GEEMAP_INSTALL_CONFIRMATION_REQUIRED`，不执行安装或静态回退。
  地图渲染失败返回 `MAP_FAILED`；静态回退仅在用户已明确接受时执行。

安装后运行同一代码即可生成地图，不需更换算法。不得把静态图或测试空壳HTML声称为
真实交互地图。

## helper调用

生成分享版与复现版时保留 `gee_map_preview.py` 中的 `load_folium_backend()` 逻辑：
仅在导入期间选择Folium后端，并恢复原进程环境变量；必要时临时解析同名底图模块再恢复。
此兼容处理不安装软件、不改第三方库文件、不改变科研结果，不能依赖作者机器的库补丁。
导入失败需区分真正缺依赖和已安装软件的运行错误；后者先报告诊断，不能自动重装。

`scripts/gee_map_preview.py`的save_interactive_map接受最终ee对象，不初始化身份、不Export。
roi应为经过检查的ee.FeatureCollection（用style生成透明边界）；参考和结果应为ee.Image。
Coverage/Mask由科研逻辑提供。边界/中心定位只请求有界centroid/bounds，不拉完整ROI到本地。

```python
map_record = save_interactive_map(
    roi=roi, reference_image=reference_image, result_image=result_image,
    reference_vis={"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3},
    result_vis={"bands": ["NDVI"], "min": -0.2, "max": 0.8,
                "palette": ["#440154", "#21918c", "#fde725"]},
    coverage_image=valid_mask,
    coverage_vis={"min": 0, "max": 1, "palette": ["#c43c39", "#38a169"]},
    output_path=artifact_root / "preview" / "map.html",
    open_browser=True,
)
```

不要为地图创建垃圾Asset。地图视觉核验不替代research-rules的统计和真实性检查。
