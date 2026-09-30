# GDMLEditor

**GDML 几何编辑器** —— 在交互式 3D 视图中导入、浏览、编辑并导出 Geant4 GDML 几何，并支持碰撞检查与场景构建。

> **版本 0.1.0** ｜ 最后更新 2026-09-30 ｜ 英文版：[README.md](README.md)

## 概述

GDMLEditor 是基于 **PyQt6 + VTK** 的 [GDML](https://geant4.web.cern.ch/support/source_geometry_manuals)（Geometry Description Markup Language）3D 几何编辑器，属于 Easy2Rad 项目的一部分，支持 GDML 文件解析、3D 可视化、浏览、编辑与导出。

> **平台说明**：目前仅在 **Windows** 上开发和测试，Linux 支持会在后续版本中验证。

## 功能特性

### 文件操作

- **导入 GDML** —— 支持单个 / 多个 `.gdml` 文件，大文件在后台线程解析
- **导出 GDML** —— 完整导出 GDML，保留原始 XML 结构与用户的编辑覆盖层
- **多文件合并** —— 多次导入的场景树自动合并

### 3D 可视化

- **VTK 渲染** —— 基于 VTK + OpenGL 2 后端的硬件加速 3D 渲染
- **交互** —— 鼠标旋转 / 平移 / 缩放，节点拾取（单击高亮）
- **视图控制** —— X/Y/Z 轴视图、正交 / 透视切换、Fit All、Reset View
- **裁剪面** —— X/Y/Z 三轴实时裁剪，滑块控制位置
- **显示效果** —— 边线开关、透明开关、深浅色主题
- **GPU 诊断** —— 启动时打印 OpenGL 信息；优先使用屏幕内 GPU 上下文，失败时回退到离屏软件渲染

### 场景构建

- **探测器** —— **🧊 Box** / **🌐 Sphere** 生成一个简单的探测器体，作为独立的 GDML 文件，并在主视图中连同它将获得的世界包围盒一起预览
- **实体预览** —— 右键实体 → 独立的 VTK 预览窗口
- **删除 / 清空** —— 从树中移除单个已导入文件，或用 **🗑️ Clear All** 清空场景

### 编辑

- **位移编辑** —— 对 physvol 与文件节点做位置 / 旋转覆盖（非破坏性）
- **世界体重置** —— 自动计算场景包围盒并调整 world volume
- **材料赋值** —— NIST 与自定义材料的批量赋值
- **本地材料** —— 在树中创建 / 编辑 / 删除自定义元素、化合物、混合物；支持 JSON 导入导出

### 碰撞检测

- **基于 AABB** —— 快速轴对齐包围盒重叠检测
- **全量 / 采样模式** —— 全量 O(n²) 或随机 5% 采样（最少 2 对、最多 50 对）
- **跨文件保证** —— 采样模式下至少包含一个跨文件零件对
- **批量高亮** —— 发生碰撞的实体在 3D 场景中高亮

### 支持的实体类型

| 类型 | 解析 | 渲染 | 导出 | 说明 |
|------|:-----:|:------:|:------:|-------|
| box | ✅ | ✅ | ✅ | 长方体 |
| sphere | ✅ | ✅ | ✅ | 支持 rmin/startphi/deltaphi/starttheta/deltatheta |
| orb | ✅ | ✅ | ✅ | 全球（单一半径） |
| tube / tubs | ✅ | ✅ | ✅ | 圆柱 / 带 phi 分段的管 |
| cone | ✅ | ✅ | ✅ | 圆锥台 |
| tessellated | ✅ | ✅ | ✅ | 三角面片 + 四边形面片 |
| torus | ✅ | ✅ | ✅ | 环体 |
| ellipsoid | ✅ | ✅ | ✅ | 非均匀缩放 |
| polycone | ✅ | ✅ | ✅ | 多段圆锥（近似渲染） |
| genericPolycone | ✅ | ✅ | ✅ | 由通用参数生成的 polycone |
| 其他约 25 种类型 | ✅ | ❌ | ✅ | 保留原始 XML，可无损往返 |
| Bool / multiUnion | ✅ | ❌ | ✅ | 保留原始 XML |

> 导入不支持的实体类型时会弹出 `QMessageBox`，列出全部不支持项。

## 运行要求

| 依赖 | 版本 |
|---|---|
| Python | >= 3.10 |
| PyQt6 | == 6.4.2（由 `environment.yml` 固定，更高版本未测试） |
| VTK | >= 9.2.0 |
| numpy | 任意较新版本 |

> 本模块没有 `requirements.txt`，`environment.yml` 即为参考环境。

## 安装

```bash
conda env create -f environment.yml
conda activate easy2rad-env
python main.py
```

## 使用说明

1. **导入**：点击工具栏 **📂 Import GDML**，选择一个或多个 `.gdml` 文件
2. **浏览**：左侧树面板查看层级，中央 3D 视图查看几何
3. **选中**：点击树节点或在 3D 视图中拾取，右侧属性面板显示详情
4. **编辑位移**：右键树节点 → 位移对话框（位置 / 旋转）
5. **碰撞检查**：点击 **🔌 Interference** → 选择实体 → Run
6. **赋材料**：点击 **🧪 Material** → 批量赋值对话框
7. **添加探测器**：点击 **🧊 Box** / **🌐 Sphere**，生成独立的探测器 GDML 文件
8. **重置世界体**：点击 **📐 Redefine World**，把 world volume 调整到场景大小
9. **导出**：点击 **💾 Export GDML**，选择保存路径

> 左侧面板标题为 `Project Tree`，其根行命名为 `Project of GDMLEditor`，导入的几何都挂在该根行下。

## 项目结构

```
gdmleditor/
├── main.py                     程序入口（QApplication + 主窗口）
├── app/
│   └── main_window.py          主窗口：树与场景编排
├── core/                       核心层 —— 数据模型与逻辑
│   ├── gdml_agent.py           单例调度器（解析树 + 编辑覆盖层）
│   ├── gdml_parser.py          XML → GdmlNode 树
│   ├── gdml_tree.py            GdmlNode 类型 + Placement
│   ├── gdml_writer.py          节点树 → XML
│   ├── gdml_evaluator.py       数学表达式求值
│   ├── detector_factory.py     长方体 / 球探测器生成
│   ├── materials_lib.py        NIST + 本地材料库
│   └── collision_detector.py   AABB 碰撞检测
├── ui/                         Qt 界面层
│   ├── vtk_widget.py           内嵌 VTK 3D 视图
│   ├── vtk_view_window.py      独立 VTK 预览窗口
│   ├── project_tree.py         树面板
│   ├── property_panel.py       属性面板
│   ├── ribbon_toolbar.py       Ribbon 工具栏
│   ├── interference_panel.py   碰撞检测面板
│   ├── detector_dialog.py      添加探测器对话框
│   ├── transform_dialog.py     位置 / 旋转对话框
│   ├── redefine_world_dialog.py  世界体调整对话框
│   └── ...                     材料相关对话框等
├── vtk_engine/                 渲染引擎
│   ├── vtk_scene.py            场景管理
│   └── vtk_solid_factory.py    实体类型 → vtkActor 工厂
├── utils/
│   └── logger.py               异步日志
├── tests/                      导出往返测试
├── docs/                       开发者文档
├── icon/                       应用图标（gdmleditor.svg）
├── output/                     导出的 GDML 文件
├── data/                       元素与材料数据文件
│   ├── element.xml
│   ├── nist.txt
│   └── local_materials.json    用户保存本地材料时生成
├── environment.yml             conda 环境（名称 easy2rad-env）
├── README.md                   英文说明
└── README.zh.md                本文件
```

## 架构

应用分层：`app/` 负责工作流编排，`core/` 承载数据模型与逻辑，`vtk_engine/` 把模型转换为
actor，`ui/` 存放 Qt 组件，`utils/` 提供公共辅助。解析树不会被就地修改，
所有用户编辑都保存在由 `GdmlAgent` 管理的覆盖层中。

### 数据流

1. **导入**：文件 → `GdmlParser.parse_file()` → `GdmlNode` 树 → `GdmlAgent`
2. **渲染**：`GdmlAgent.get_root_node()` → `VtkScene.build_from_tree()` → `VtkSolidFactory` 创建 `vtkActor` → `vtkRenderer`
3. **编辑**：界面 → `GdmlAgent`（覆盖层）→ 场景重建
4. **导出**：`GdmlWriter.write()` → 节点树 + 覆盖层 → GDML XML

## 已知限制

- 仅上表列出的实体类型会被渲染；另外约 25 种（`polyhedra`、`xtru`、`cutTube`、`tet`、
  布尔运算、`multiUnion`、`scaledSolid` 等）仅解析并原样写回，不参与 3D 绘制，
  导入时会弹出 **"Incomplete Geometry Parsing"** 对话框列出。
- `<materials>` 为简化解析（MVP），只读取 `name` 与密度值。
- 表达式求值中未定义的标识符会被替换为 `0`。
- 碰撞检测为纯 **AABB**：全量 O(n²) 或随机 5% 采样（最少 2 对、最多 50 对），
  属于保守近似，并非精确相交计算。
- 尚未实现（详见 `docs/09_known_limitations.md`）：`divisionvol`、`replicavol`、
  `parameterised`、`loop`、`matrix`、`bordersurface` / `skinsurface`、`isotope`。
- 小于 500 KB 的文件在主线程解析，更大的文件使用后台线程，进度对话框为
  marquee 样式且不可取消。

## 开发说明

- **实例克隆（Geant4 模式）** —— 每个 `<physvol>` 都会递归克隆一棵子树，
  源体积定义仍保留在逻辑体积库中。
- **编辑覆盖层** —— `GdmlAgent` 维护 `_placement_overrides` / `_material_overrides`
  字典；渲染层通过注入 `VtkScene` 的 override provider 获取覆盖信息，
  因此原始解析树始终不被改动。
- **后台线程** —— 500 KB 以上的文件由 `_ImportWorker` 在 `QThread` 中解析
  （`file_parsed` / `all_done` 信号回主线程）；进度对话框会保持到树与 3D 场景重建完成。
- **GPU 自动探测** —— 优先使用屏幕内 GPU 上下文，失败时回退到离屏软件渲染
  （`SetOffScreenRendering(True)`），并打印一次 OpenGL 信息便于诊断。
  `VtkViewWindow` 上不能使用任何 QSS，否则会破坏 OpenGL 合成导致白屏。
- **单例** —— `GdmlAgent`、`VtkSolidFactory`、`AsyncLogger`；`MaterialsLib` 为
  单例式实现，元素库挂在类级别。
- **日志** —— `AsyncLogger` 通过 `log_received` 信号广播，在挂载日志控件前会先缓存消息。
- **无损往返** —— 不支持的实体以原始 XML 保存，保证导出保真。

## 相关文档

- **架构总览**：[docs/01_architecture_overview.md](docs/01_architecture_overview.md)
- **VTK 渲染引擎**：[docs/03_vtk_rendering_engine.md](docs/03_vtk_rendering_engine.md)
- **碰撞 / 干涉检测**：[docs/06_collision_detection.md](docs/06_collision_detection.md)
- **后台线程加载**：[docs/07_background_threading.md](docs/07_background_threading.md)
- **材料系统**：[docs/08_material_system.md](docs/08_material_system.md)
- **已知限制与后续方向**：[docs/09_known_limitations.md](docs/09_known_limitations.md)
- **解析 / 写出能力**：[docs/parser_capabilities.md](docs/parser_capabilities.md)
- 本文件的英文版：[README.md](README.md)

## 许可

[MIT](LICENSE) © ready2run

## 致谢

- [OpenCASCADE Technology](https://dev.opencascade.org/) —— CAD 内核
- [GMSH](https://gmsh.info/) —— 有限元网格生成器
- [VTK](https://vtk.org/) —— 可视化工具包
- [PythonOCC](https://github.com/tpaviot/pythonocc-core) —— OCC 的 Python 绑定
- [Geant4](https://geant4.web.cern.ch/) —— GDML 几何格式
- [CodeBuddy](https://www.codebuddy.ai/) 与 [DeepSeek](https://deepseek.com/) —— 本项目开发过程中的 AI 辅助
