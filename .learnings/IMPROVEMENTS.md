# 可优化项

判断标准：这件事我做了 2 次以上手写，或每次都要靠记忆。

| 优先级 | 项 | 现状 | 目标 | 状态 |
| --- | --- | --- | --- | --- |
| 高 | 答案比对 | 每套卷临时写一个 `verify_*.py`，只有答案串不同 | `scripts/verify_answers.py --batch b.json --key "1-5:BABAC,..."`，不一致退出码 1 | 待做 |
| 中 | 交接单 | 手写 md，字段与 batch 重复，曾漏登记 OCR 修正 | 从 batch + 切分结果套模板生成 | 待做 |
| 中 | 媒体部署 | 手工 mkdir + 逐个 scp + 逐个 curl 验 200 | 一个脚本：传完自动点数 + 抽样验证 | 待做 |
| 低 | 全流程 | 每年手工串 7–8 步 | `make_batch.py <docx> <mp3> <年>`；题型/答案表仍由人或模型产出 | 待做 |

## 已完成的优化

| 项 | 做法 |
| --- | --- |
| 音频切分 | 固化为 `scripts/cut_audio.py`（分层报告 / 转写 / 锚点切分 / 回读验证四合一）；2026-10-22 增 `--ends` 显式终点与 UTF-8 解码 |
| 原卷提取 | 固化为 `scripts/extract_docx.py`（正文 + 表格 + 图片一次出） |
| 附件合并 | 固化为 `scripts/patch_attachments.py`（先 dry-run 再提交） |
| 打标默认值 | 固化为 `scripts/apply_type_tags.py`（按题型补空缺，题目特有考点仍逐题判断） |
| 打标体检 | 固化为 `scripts/check_tags.py`（空标签 / 禁标维度 / 停在父节点未下钻） |
| 子题补标 | 固化为 `scripts/fill_subtags.py`（阅读按设问判定 + 其余继承组级，语法选择走 --map） |
| 拼写细分 | 固化为 `scripts/spell_pos.py`（列答案 → 人工定词性 → 落 词汇辨析/<词性>） |
| 草稿重打 | 固化为 `scripts/retag_drafts.py`（禁标纠正 + 维度兜底 + 逐篇覆盖，默认 dry-run） |
| 知识点检索 | 固化为 `scripts/find_kp.py` + `references/knowledge-catalog.json`（514 节点离线可查） |

