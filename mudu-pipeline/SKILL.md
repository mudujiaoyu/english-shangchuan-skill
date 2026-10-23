---
name: mudu-pipeline
description: 木牍录题总编排：把「提取 → 切音频 → 题型 → 知识点 → 难度分类 → 上传」六个阶段包串成流水线，定义交接契约并汇总校验。
metadata:
  category: workflow
  part_of: mudu-pipeline
  stage: 0
---

# 木牍录题流水线（编排）

把一份原卷送进题库，拆成 6 个阶段包，每步产出固定文件交给下一步。

```
mudu-extract → mudu-audio → mudu-type-map → mudu-knowledge → mudu-meta → mudu-upload
   01_source     02_audio      03_types        04_knowledge     05_meta     06_batch/07_upload
```

## 何时用哪个包

| 阶段 | 技能 | 什么时候单独用 |
| --- | --- | --- |
| 1 提取 | `mudu-extract` | 只有新卷要解析；或只想把 PDF 转成文本/图片 |
| 2 切音频 | `mudu-audio` | 听力要重切、去试音、验证切点 |
| 3 题型 | `mudu-type-map` | 题型/子类拿不准，或要核对 `subtypes` |
| 4 知识点 | `mudu-knowledge` | 补标、重标、体检、查节点 |
| 5 难度分类 | `mudu-meta` | 补难度、改分类、生成待编辑清单 |
| 6 上传 | `mudu-upload` | 查重、预检、部署媒体、POST、补附件 |

## 交接契约（每步必须产出，下一步只读这些）

| 步骤 | 产出 | 关键字段 |
| --- | --- | --- |
| 01 | `01_source/正文.txt`、`media/`、`structure.json` | `sections[].type/questions`、`image_questions` |
| 02 | `02_audio/li-XX.mp3`、`audio_map.json` | `{unit_id: {file, duration, covers}}` |
| 03 | `03_types/types.json` | `{unit_id: {type, subtypes}}` |
| 04 | `04_knowledge/knowledge.json` | `{unit_id: {answer, explanation, knowledge, subs}}` |
| 05 | `05_meta/meta.json` | `{unit_id: {difficulty, difficultyValue, categories}}` |
| 06 | `06_batch/batch_<年>.json` | 完整批次对象 |
| 07 | `07_upload/receipt.json` | `{staging_id, units, subs, confirmed:false}` |

**上游缺字段就停下来问，不要自行补造。**

## 汇总校验

```bash
python scripts/verify_package.py            # 检查 6 个包是否齐全、脚本能否编译、契约是否完整
python scripts/verify_package.py --run      # 额外跑每个包的 smoke test
```

`--run` 会执行：`find_kp.py`（知识点包）、`check_tags.py`（体检）、`assign_meta.py --report`（难度包）、
`check_duplicates.py`（上传闸门），确认每个包在真数据上能跑。

## 顺序与跳过规则

- 没有听力 → 跳过 02，`audio_map.json` 写空对象。
- 没有解析 → 04 的 `explanation` 留空，不编造。
- 无子题（单题单元）→ 04 只写组级 `knowledge`。
- 已入库要改 → 不要重传，直接调对应包的 `--apply` 打补丁（PATCH 草稿）。

## 身份边界（跨所有包）

- 不能：`GET /api/uploads`、`POST /uploads/{id}/confirm`、`DELETE /api/questions/{id}`、
  `publish`、`withdraw`、建正式知识点节点。
- 能做：目录读、`POST /api/uploads`、`PATCH /api/questions/{id}`（仅草稿）、`POST /compositions/export`。

## 全流程收尾

1. `verify_package.py` 全绿；
2. `check_duplicates.py` 返回 0；
3. `preflight_check.py` 0 失败；
4. POST 得到 staging id；
5. 把 staging id、单元/子题数、待编辑项写进 `receipt.json` 和交接单。
