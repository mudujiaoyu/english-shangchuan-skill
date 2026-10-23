# mudu-question-upload

木牍教育英语题库录入技能。一份原卷 → 六步 → 进题库，全部封装在一个技能内。

```
① 解析  ② 听力  ③ 题型  ④ 知识点  ⑤ 难度分类  ⑥ 上传
 01_source → 02_audio → 03_types → 04_knowledge → 05_meta → 06_batch
```

## 目录

```
SKILL.md                    总入口：流程、交接契约、六步要点、命令
references/
  stages/01-extract.md      ① 原卷解析（docx / PDF 无文字层）
  stages/02-audio.md        ② 听力切段
  stages/03-type-map.md     ③ 题型与子类
  stages/04-knowledge.md    ④ 答案与知识点
  stages/05-meta.md         ⑤ 难度与分类
  stages/06-upload.md       ⑥ 组装与上传
  structure.md              卷面结构识别
  pdf-extraction.md         PDF 渲染/分栏/切图
  audio-splitting.md        听力分层与锚点
  type-subtypes.md          26 主类 × 子类判定
  knowledge-tagging.md      七维度打标
  knowledge-matching-rules.md 分支匹配细则
  knowledge-catalog.json    514 个知识点节点
  type-knowledge-map.json   题型 → 知识点默认映射
  difficulty-category.json  难度/分类规则
  upload-api.md             接口、错误码、陷阱
scripts/
  01-extract/  extract_docx.py  pdf_extract.py
  02-audio/    cut_audio.py
  04-knowledge/ find_kp.py  apply_type_tags.py  fill_subtags.py
                spell_pos.py  retag_drafts.py  check_tags.py
  05-meta/     assign_meta.py
  06-upload/   check_duplicates.py  preflight_check.py  patch_attachments.py
  verify_package.py          自检 + smoke test
```

## 自检

```bash
python scripts/verify_package.py --run
```

校验阶段文档、共享参考、脚本编译，并跑 `find_kp` / `check_tags` / `assign_meta` / `check_duplicates` 四组 smoke test。

## 安装

把本目录放进技能目录（如 `~/.agents/skills/`），新会话即可在技能列表看到 `mudu-question-upload`。

## 边界

Harness 只能：读目录、`POST /api/uploads`、`PATCH /api/questions/{id}`（仅草稿）、提知识点建议、导出。
确认、发布、删除、列表读取必须人工在后台完成。
