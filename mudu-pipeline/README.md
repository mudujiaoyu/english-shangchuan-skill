# english-shangchuan-skill

木牍教育英语题库「录题」技能（mudu-question-upload）的发布仓库。

## 这是什么

把一份原卷（.docx/.pdf + 听力 mp3）整理成题库 API 批次对象并写入上传暂存：
提取正文/表格/图片 → 切分听力音频（去试音）→ 26 类题型与子类映射 → 答案与解析核对 →
知识点打标（七维度、词性细分、子题继承）→ 生成批次 → 上传前查重与预检 → POST /api/uploads。

## 安装

把本仓库内容放到 Agent 技能目录，目录名保持 `mudu-question-upload`：

- Windows: `%USERPROFILE%\.agents\skills\mudu-question-upload\`
- 其他: `~/.agents/skills/mudu-question-upload/`

要求：`python`、`ffmpeg`、`ffprobe`、`ssh`、`scp`、`curl`（转写功能另需 `faster-whisper`）。

## 结构

| 路径 | 说明 |
| --- | --- |
| `SKILL.md` | 主文档：流程、身份边界、题型映射、知识点打标、自检、坑 |
| `references/structure.md` | 怎么从原卷推断结构（三步） |
| `references/type-subtypes.md` | 26 主类 × 子类检索表 |
| `references/type-knowledge-map.json/.md` | 题型 → 默认知识点 |
| `references/knowledge-matching-rules.md` | 知识点逐分支匹配细则 |
| `references/knowledge-tagging.md` | 打标原则与禁标矩阵 |
| `references/knowledge-catalog-1.0.md/.json` | 知识点目录原文与 514 节点索引 |
| `scripts/*.py` | 提取、切分、查重、预检、打标、检索脚本 |
| `.learnings/` | 内部问题台账（ISSUES/IMPROVEMENTS/CHANGELOG） |

## 快速用法

```bash
python scripts/extract_docx.py 原卷.docx out/
python scripts/cut_audio.py --audio 听力.mp3 --report
python scripts/preflight_check.py --batch batch.json --insert
python scripts/check_duplicates.py --batch batch.json
```

> 仓库里的 `.learnings/` 是踩坑记录，随技能一起版本化，便于追溯规则为什么这样定。
