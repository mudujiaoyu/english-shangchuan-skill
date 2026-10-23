# 上传接口与错误码

## 端点

| 方法 | 路径 | 作用 | 谁能用 |
| --- | --- | --- | --- |
| POST | `/api/uploads` | 建批次，进 `pending_confirmation` | Harness（scope `draft`） |
| GET | `/api/uploads` | 暂存列表 | **仅人工**（Harness 403） |
| POST | `/api/uploads/{id}/confirm` | 逐题确认，生成草稿 | **仅人工**（Harness 403） |
| PATCH | `/api/questions/{id}` | 改草稿 | Harness（仅 draft） |
| GET | `/api/questions` | 查已发布 | Harness |
| POST | `/api/catalog/knowledge-proposals` | 提新增知识点建议 | Harness |

## 批次对象

```json
{"subject_id":"english","upload_mode":"source","upload_target":"中考真题",
 "batch_id":"anhui-2022-english-zhenti","name":"2022年…","items":[…]}
```

体积上限 **2,000,000 字节**（UTF-8）。超了拆两批。

## 错误码对照

| HTTP | error | 原因 | 修法 |
| --- | --- | --- | --- |
| 400 | `invalid_request` | 附件/表格/知识点校验抛错 | 跑 `preflight_check.py` 定位 |
| 400 | `invalid_json` | 请求体不是合法 JSON | 检查 BOM、编码 |
| 400 | `invalid_source_type` | 题源不在 11 类 | 用框架里的原文 |
| 400 | `invalid_unit_kind` | 不是 standalone/group | 改正 |
| 409 | `question_id_exists` | 该 ID 已确认过 | 不要重传，PATCH 草稿 |
| 409 | `duplicate_question_id` | 批内 ID 重复 | 去重 |
| 409 | `knowledge_confirmation_required` | 知识点名不在目录 | `find_kp.py` 查真实名称 |
| 409 | `staging_already_confirmed` | 该暂存已确认 | 无需再确认 |
| 403 | `human_confirmation_required` | Harness 调 confirm | 只能人工 |
| 413 | `payload_too_large` | 超 2MB | 分批 |

## 两个静默失败

1. **附件 `placement` 只能是 `question`/`option`/`answer`/`explanation`**。
   写成 `stem` → `invalid_attachment` → 400 `invalid_request`，前端只弹一句就吞掉，
   人工点「逐题确认」看起来像没反应。音频用 `question`，选项图用 `option` + `optionKey`。
2. **知识点只认名称或 ID**。提交完整路径（`词汇/词汇辨析/动词辨析`）会 409。

## 确认之后的顺序陷阱

- 同一批 `id` 不能再走第二次 `POST /api/uploads`：v1 确认后传 v2 会 409。
  要改内容只能 `PATCH` 现有草稿。
- `PATCH attachments` 是**整体替换**：先读现有数组，合并后再提交。
- `PATCH filterMetadata` 同样是**整体替换**：补一个标签要带上其余标签。
- 发布需要 `explanation` 齐全，否则 `publish_blocked: missing_explanation`。

## 媒体

- 目录：`/home/ubuntu/mudu-quiz/static/source-media/<批次>/`，URL 用 `/source-media/<批次>/xxx.mp3`。
- 传完必须抽验 `curl -o NUL -w "%{http_code}"` 返回 200；scp 混合扩展名会部分失败，按 basename 核对数量。
