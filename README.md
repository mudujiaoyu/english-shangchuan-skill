# mudu-skills — 木牍英语题库录入技能包

一份原卷从「文件」到「进题库」的完整流水线，拆成 6 个阶段包 + 1 个编排包。
每个包只干一件事，产出固定文件交给下一步。

```
mudu-extract → mudu-audio → mudu-type-map → mudu-knowledge → mudu-meta → mudu-upload
   01_source     02_audio      03_types        04_knowledge     05_meta    06_batch/07_upload
```

| 包 | 负责 | 主要产出 |
| --- | --- | --- |
| `mudu-extract` | 原卷解析：docx/pdf → 正文、表格、图片、结构清单 | `01_source/` |
| `mudu-audio` | 听力整卷切段：分层、锚点、去试音、回读校验 | `02_audio/` |
| `mudu-type-map` | 匹配 26 主类 + 子类（建议存储值） | `03_types/types.json` |
| `mudu-knowledge` | 答案/解析核对 + 七维度知识点打标 | `04_knowledge/knowledge.json` |
| `mudu-meta` | 难度（difficulty/difficultyValue）与分类（优选题/易错题） | `05_meta/meta.json` |
| `mudu-upload` | 组装批次、查重、预检、媒体、POST、PATCH | `06_batch/`、`07_upload/` |
| `mudu-pipeline` | 交接契约、顺序规则、汇总校验 | `verify_package.py` |

## 汇总校验

```bash
python mudu-pipeline/scripts/verify_package.py        # 目录/契约/编译
python mudu-pipeline/scripts/verify_package.py --run  # 再跑各包 smoke test
```

## 安装

把 7 个目录放进技能目录（例如 `~/.agents/skills/`），重启会话即可在技能列表看到。

## 边界

Harness 身份只能：读目录、`POST /api/uploads`、`PATCH /api/questions/{id}`（仅草稿）、
提知识点建议、导出。确认、发布、删除、列表读取必须人工在后台完成。

## 约定

- 题型只能取 26 个固定主类，子类只能取框架里列出的值，不得新增/改名。
- 知识点必须落在目录叶子上，「词汇/词汇辨析」这类父节点不算。
- 难度按 `developer.md`：`difficulty` 取易/中/难，`difficultyValue` 0–1，未知留空不猜。
- 上传前必须过查重与预检两道闸门。
