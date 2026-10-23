# 组装与上传（06-upload）

**输入**：02–05 的全部产出。
**输出**：`06_batch/batch_<年>.json` + `07_upload/receipt.json`

## 6.1 批次对象

```json
{"subject_id":"english","upload_mode":"source","upload_target":"中考真题",
 "batch_id":"anhui-2022-english-zhenti","name":"2022年…","items":[...]}
```

每个 item 必填：`id`（`AH-<年>-<三位>`）、`unit_kind`、`stem`、`options`、`answer`、
`type`、`knowledge`、`knowledgeIds`、`filterMetadata{subtypes,categories,region,difficultyValue}`、
`difficulty`、`source_type`、`year`、`source`、`version`、`authorization`、`attachments`。

题组另加 `subquestions`；表格题另加 `materialBlocks`。

## 6.1b 一条命令跑完（推荐）

```bash
python scripts/06-upload/run_upload.py --batch 06_batch/batch.json \
    --media-dir media_upload/ --answers 01_source_ans/answers.json
```

依次跑 **本机体检（四项并行）→ 服务器闸门（一次会话）→ 媒体部署与校验 → POST → 写 receipt**，
任一闸门失败即停，不会带病上传。加 `--no-post` 只体检不上传。

| 阶段 | 做法 | 耗时（34 单元批次实测） |
| --- | --- | --- |
| 本机体检 | 排版/标签/阅读/发布闸门/答案 五项**并行** | 0.06s（原 0.2s 串行） |
| 服务器闸门 | 查重 + 预检 + 同 ID 统计 + 远端媒体清单，**一次 scp 两个文件 + 一次 SSH** | 1.6–2.3s（原 3.8s，含复制 5MB 库） |
| 媒体 | 只传**远端缺失**的文件（清单由闸门带回），URL **并发 + Range 只取首字节** | 1.2s（全部已就位时）；首次全量约 2.8s |
| 上传 | `POST /api/uploads` | 0.1s |

合计 **热路径 2.3s / 冷路径 4.3s**（原来逐脚本串行 6.9–8.9s）。

**不要优化错地方**（实测）：

| 操作 | 耗时 | 结论 |
| --- | --- | --- |
| SSH 往返 / `python3 -c pass` / `import backend` | 0.36 / 0.38 / 0.42s | 远程步骤有 0.4s 固定成本，**能合并就合并** |
| 全库 379 行查重指纹 | 0.02s | 不是瓶颈，别加缓存 |
| `current_knowledge_points`（522 节点） | 0.002s | 不是瓶颈 |
| 20 个 URL 串行 curl → 并发+Range | 6.3s → 1.8s | RTT 主导，必须并发 |
| 9 个小文件 scp / tar / 并行 scp | 1.9 / 1.3 / 6.1s | tar 略快但引入临时文件；**并行 scp 反而更慢** |

注意：Windows 下 `ssh ... python3 -` 用 subprocess 的 `input=` 传脚本**不可靠**（实测 stdin 为空），
所以闸门脚本与批次走 scp 文件而不是管道。

细项校验仍可单独跑（`check_answers` / `check_text` / `check_tags` / `audit_reading` / `publish_check` /
`check_duplicates` / `preflight_check`），`run_upload.py` 只是把它们编排起来。

## 6.2 自检（脚本化，别靠眼睛）

```bash
python scripts/06-upload/check_answers.py --batch b.json --answers 01_source_ans/answers.json
python scripts/06-upload/check_text.py --batch b.json
python scripts/06-upload/check_structure.py --batch b.json    # 结构：unit_kind / 子题 / 材料
python scripts/04-knowledge/check_tags.py --batch b.json
python scripts/06-upload/audit_reading.py --batch b.json      # 阅读：选项图/材料图/大意/空答案
```

- [ ] ID 唯一、格式统一
- [ ] 答案与答案卷逐题一致（`check_answers.py` 退出码 0，客观题不一致数 0）
- [ ] 题型在 27 主类内、子类在框架内
- [ ] `knowledge` 能解析成 ID（服务端只认名称或 ID，路径会 409）
- [ ] 附件 `placement` 只能是 `question/option/answer/explanation`
- [ ] 体积 < 2 MB
- [ ] **阅读类图片层级正确**：材料图挂单元、选项图挂子题（见 6.2b）

## 6.2b 阅读题的两类图片，挂错不会报错只会「看不见」

| 图的用途 | 挂在哪 | 字段 | 前端行为 |
| --- | --- | --- | --- |
| 材料本身是图（杂志目录、海报、表格、漫画） | **单元** `attachments` | `placement:"question"` | 渲染在材料区 |
| 某道小题的选项是图（Which picture…） | **子题** `subquestions[i].attachments` | `placement:"option"` + `optionKey:"A"` | `selectionSubquestionMarkup` 把子题对象交给 `mediaMarkup`，只认子题级 |

**挂错的表现**：选项只剩 `A.` `B.` `C.` `D.` 空壳，图一张都不出现；接口照样 200，没有任何报错。
2026-10-23 体检时 AH-2025-056 第 57 题、AH-2023-056 第 57 题都是这个错。

**材料是图片时**：`material` 留空，用 `placement:"question"` 的图承载（必要时加 `materialBlocks` 保留表格结构），
不要再手打一份全文转写——既是重复，又把转写错误带进题库。

`audit_reading.py` 与 `preflight_check.py` 都会拦这类错误（预检里报「选项图疑似挂到了单元上」）。

## 6.3 查重（硬闸门）

```bash
python scripts/check_duplicates.py --batch batch.json
# 0 放行；1 有重复，禁止上传；2 连接错误
```

三个维度任一命中即判重：ID 已存在、同年同题号、内容指纹相同。**重复就不要传**，改 PATCH 现有草稿。

## 6.4 上传前预检（用服务端同一套校验器）

```bash
python scripts/preflight_check.py --batch batch.json --insert
```

在库副本上跑 `prepare_question_knowledge` / `normalize_material_blocks` / `normalize_attachments` /
`normalize_filter_metadata`，并模拟确认写入。**这一步能在 POST 之前暴露 400。**

## 6.5 媒体与上传

```bash
ssh … "mkdir -p /home/ubuntu/mudu-quiz/static/source-media/<批次>/"
scp li-*.mp3 …:/home/ubuntu/mudu-quiz/static/source-media/<批次>/
curl -o NUL -w "%{http_code}" http://127.0.0.1:8089/source-media/<批次>/li-01.mp3   # 200
curl -X POST http://127.0.0.1:8089/api/uploads -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json; charset=utf-8" --data-binary @batch.json
# → 201 {"id":"<staging>","stage":"pending_confirmation"}
```

## 6.6 确认之后

- **同一批 id 不能二次确认**：v1 确认后再传 v2 会 409 `question_id_exists`。
- **PATCH `attachments` 是整体覆盖**，先读现状再合并。
- 确认与发布只能人工做；AI 调 confirm 会 403 `human_confirmation_required`。

## 6.6b 排版体检

```bash
python scripts/06-upload/check_text.py --ids AH
python scripts/06-upload/check_text.py            # 全库
```

查：全角空格空档、双空格、括号不配对/中英混用、破折号、中文标点入英文句、引号不配对、
重复标点、下划线过短、选项标点混用（`A．` 应为 `A.`）。只报告，不阻断。

## 6.7 发布闸门（确认之后才生效）

草稿确认后仍不能发布，除非这五项齐全：

| 阻断码 | 含义 |
| --- | --- |
| `missing_stem` | 题干为空 |
| `missing_answer` | 答案为空 |
| `missing_question_type` | 题型为空 |
| `missing_knowledge` | 知识点为空 |

```bash
python scripts/06-upload/publish_check.py --ids AH-2022
python scripts/06-upload/publish_check.py --batch b.json
```

该脚本区分「真缺子类」和「该主类本就没有子类」：`听力其他`、`听力短文理解`、`听力信息转换`
在框架里没有子类，`subtypes` 留空是正常的，不算缺陷。

组题还有两条硬要求：

| 阻断码 | 含义 | 常见修法 |
| --- | --- | --- |
| `incomplete_group_unit` | group 题没有 `material` 或没有子题 | 听力组无印刷材料时写占位 `（听力材料见音频）` |
| `incomplete_group_subquestions` | 有子题缺 `stem` 或 `answer` | 完形/补全对话的空在材料里，子题 stem 从材料截含 `__N__` 的句子，截不到写「第N空」 |

**截句做子题 stem 的两个坑**：
1. 从句中截取会带出**单边引号**（`“We’ve seen a growing　42　in learning Chinese.`），
   `check_text.py --batch` 会报「引号不配对」。截完把不成对的引号去掉，别留着。
2. 空档标记写成 `__31__` 时会被「下划线过短」误报；`check_text.py` 已把 `__数字__` 先统一按 6 个下划线处理。

## 6.2b-2 组题子题 stem 不要重复材料里已有的标号

补全对话这类组题，材料里已经用 `1.______` `2.______` 标好空号，子题再写「第1空」「第2空」
就是重复信息，前端会同时显示「第1空」和材料里的「1.」。

- **正确**：子题 stem 只放空档本身 `______`，靠 `number` 区分是第几个空；
- **不要**：`第1空` / `第N空`（除非材料里没有标号，必须靠子题指明位置）；
- 服务端 `publish_blockers` 要求子题 stem 非空，所以不能留空串——用 `______` 而不是 `""`；
- 例外：空位本身带内容时照抄，如音标分类的 `/ɪ/: ______`（音标是题目的一部分，不是编号）。

幂等改法（已入库的草稿）：`PATCH /api/questions/{id}` 只回传 `subquestions`，
其余字段不动；注意 harness 对**草稿**没有读权限（`GET` 返回 404），
read-modify-write 只能用自己上传时的本地批次内容，不能依赖服务端回读。

## 6.2c 结构一旦入库就改不了：建批前必须先过 check_structure

服务端对草稿的能力边界（实测 2026-10-23）：

| 想改什么 | PATCH | 说明 |
| --- | --- | --- |
| 题干/答案/解析/材料/选项 | ✅ | 普通字段直接改 |
| `subquestions`（子题内容） | ✅ | 整体替换，要先读后合并 |
| 知识点 / 附件 / filterMetadata | ✅ | 整体替换 |
| `unit_kind`（standalone ↔ group） | ❌ | 不在 PATCH 白名单，改了也不生效 |
| 删除草稿 | ❌ | `DELETE /api/questions/{id}` 对 harness 返 403 `human_delete_required` |

推论：**「独立题误建成题组」「题组误建成 5 道独立题」这类结构错误，一旦确认入库，
就只能请人工在后台删除后重传。** 而 `publish_check` 只查「group 缺材料」，
查不出「standalone 带了子题」——所以必须在**上传前**用 `check_structure.py` 拦。

判据：standalone 有 subquestions、group 缺 material/子题、子题序号不连续、
组题的选项图挂在单元上（应挂子题）。

`run_upload.py` 已把它并进本机并行体检，单跑也行：

```bash
python scripts/06-upload/check_structure.py --batch 06_batch/b.json
python scripts/06-upload/check_structure.py --ids RJ8A
```

**改结构的正确姿势**：一旦发现单元粒度定错了，不要试图 PATCH 补救——
请人工删掉那几条草稿，重新按正确粒度 `POST /api/uploads`。

**PATCH 改草稿的三条铁律**（都是整体覆盖，不是合并）：
1. `subquestions` 整体替换——只想改某题的附件/知识点，也要把**其余子题的当前值**原样带回，
   否则附件、答案、解析会被清空。改子题前先 `SELECT subquestions_json` 读现状。
2. `attachments`、`filterMetadata` 同样是整体替换，先读后合并。
3. 子题的 `textbookMappings` 里存着旧的 knowledgeIds；改子题知识点时必须连它一起替换，
   否则服务端会把旧标签（如错标的「说明文」）解析回来，表现为「改完还是旧值」。

**解析不阻断发布**：原卷/答案册有解析就跟着录入，没有就留空，不编造。`publish_check.py`
会把「解析为空」单独统计成提示，不算阻断项。

## 验收

- [ ] 查重退出码 0
- [ ] 预检 0 失败
- [ ] POST 返回 201 + staging id
- [ ] `receipt.json` 记录 staging id、单元/子题数、未做的事（未确认/未发布）
