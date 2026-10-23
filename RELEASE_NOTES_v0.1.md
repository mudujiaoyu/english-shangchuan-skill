## v0.1 — 首个可用版本

木牍教育英语题库录入技能的完整流水线：**一份原卷 → 六步 → 进题库**。

### 阶段

| 步 | 内容 | 目录 |
| --- | --- | --- |
| ① | 原卷解析（docx / 无文字层 PDF 的渲染、分栏、切图） | `references/stages/01-extract.md`、`scripts/01-extract/` |
| ② | 听力切段（分层找切点、题号锚点、去试音、回读校验） | `scripts/02-audio/` |
| ③ | 题型与子类（27 个固定主类） | `references/type-subtypes.md` |
| ④ | 答案解析 + 七维度知识点（含设题角度听力/阅读） | `scripts/04-knowledge/` |
| ⑤ | 难度与分类（按可观测特征打分，不按题型猜） | `scripts/05-meta/` |
| ⑥ | 组装、查重、预检、媒体部署、上传 | `scripts/06-upload/` |

### 关键约定

- 题型只能取 27 个固定主类，子类只能取框架里列出的值，不得新增/改名/合并。
- 知识点必须落在目录叶子；维度根节点（主题、词汇、语法、语音、语用、语篇体裁、设题角度）不写进标签。
- 主题写「一级主题 + 最后一级」；阅读与听力各有 `设题角度` 分支，同名节点必须带上级。
- 答案只认原卷；解析有就录、没有留空，不编造，也不阻断发布。
- 上传前必须过查重与预检两道闸门。

### 脚本

```
01-extract/    extract_docx.py  pdf_extract.py
02-audio/      cut_audio.py
04-knowledge/  find_kp.py  apply_type_tags.py  fill_subtags.py  spell_pos.py
               retag_drafts.py  check_tags.py  assign_angle.py
05-meta/       assign_meta.py
06-upload/     check_duplicates.py  preflight_check.py  patch_attachments.py
               publish_check.py  check_text.py
verify_package.py   自检 + smoke test
sync_skill.py       仓库 → 技能目录同步（含反向与覆盖保护）
```

### 自检

```bash
python scripts/verify_package.py --run
```

校验阶段文档、共享参考、脚本编译，并跑 `find_kp` / `check_tags` / `assign_meta` / `check_duplicates` 四组 smoke test。

### 实测数据（安徽中考 2010/2018/2019/2020/2021/2022）

- 250 个单元 / 360 个子题全部入库
- 难度与分类 250/250 覆盖
- 知识点越界 0、非叶子 0
- 发布校验 250/250 通过（服务端真实 `publish_blockers`）

### 安装

```bash
git clone git@github.com:mudujiaoyu/english-shangchuan-skill.git \
  ~/.agents/skills/mudu-question-upload
```
