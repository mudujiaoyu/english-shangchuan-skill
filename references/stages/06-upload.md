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

## 6.2 自检（脚本化，别靠眼睛）

- [ ] ID 唯一、格式统一
- [ ] 答案与答案卷逐题一致（不一致数 0）
- [ ] 题型在 26 主类内、子类在框架内
- [ ] `knowledge` 能解析成 ID（服务端只认名称或 ID，路径会 409）
- [ ] 附件 `placement` 只能是 `question/option/answer/explanation`
- [ ] 体积 < 2 MB

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

**解析不阻断发布**：原卷/答案册有解析就跟着录入，没有就留空，不编造。`publish_check.py`
会把「解析为空」单独统计成提示，不算阻断项。

## 验收

- [ ] 查重退出码 0
- [ ] 预检 0 失败
- [ ] POST 返回 201 + staging id
- [ ] `receipt.json` 记录 staging id、单元/子题数、未做的事（未确认/未发布）
