# Citations 表使用说明

本文档说明如何读写 `citations` 表。该表存储每篇论文的引文信息，`(paper_id, citation_id)` 为联合主键。

## 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| paper_id | INTEGER | 引文所属论文 ID |
| citation_id | INTEGER | 引文 ID（按论文从 1 起累计） |
| title | TEXT | 标题 |
| result_id | TEXT | 在线数据库 ID |
| year | INTEGER | 年份 |
| venue | TEXT | 期刊/会议 |
| summary | TEXT | 简介 |
| authors | TEXT | 作者列表（JSON 字符串，如 `["A", "B"]`） |
| download_status | TEXT | 下载状态：success / exists / failed / skipped |
| download_error | TEXT | 下载失败原因 |
| analysis_status | TEXT | 分析状态：analysised / completed / success 等 |
| download_link | TEXT | 下载链接 |
| cite_by_total | INTEGER | 被引用总数 |
| path | TEXT | 本地 PDF 保存路径 |

---

## 方式一：直接使用 CitationModel（model/citation_model.py）

适合脚本、批处理等不涉及用户权限的场景。

### 1. 读取某篇论文的所有引文

```python
from model.citation_model import CitationModel

cm = CitationModel()
citations = cm.get_citations_by_paper(paper_id=1)
# 返回 List[Dict]，按 citation_id 升序
```

### 2. 读取单条引文

```python
citation = cm.get_citation(paper_id=1, citation_id=2)
# 返回 Dict 或 None
```

### 3. 更新引文信息

```python
cm.update_citation(
    paper_id=1,
    citation_id=2,
    download_status="success",
    analysis_status="analysised",
    # 可传任意允许的字段：title, result_id, year, venue, summary, authors,
    # download_status, download_error, analysis_status, download_link,
    # cite_by_total, path
)
# 返回 bool
```

### 4. 其他常用方法

```python
# 某论文下引文数量
count = cm.count_by_paper(paper_id=1)

# 引文统计（总数、已下载数、已分析数）
stats = cm.get_counts_by_paper(paper_id=1)
# {"citation_count": 10, "downloaded_count": 8, "analyzed_count": 5}
```

---

## 方式二：使用 Citations 服务层（service/citations_service.py）

适合需要校验论文归属（user_id）的场景，如 API 路由。

### 1. 读取某篇论文的所有引文（含权限校验）

```python
from service.citations_service import get_citations_for_paper

citations = get_citations_for_paper(paper_id=1, user_id=当前用户ID)
# 若 paper 不属于该用户，抛出 ValueError
```

### 2. 更新引文的下载/分析状态

```python
from service.citations_service import update_citation_status

update_citation_status(
    paper_id=1,
    citation_id=2,
    download_status="success",
    analysis_status="analysised",
    download_error=None,  # 成功时清空错误信息
    user_id=当前用户ID,   # 可选，用于权限校验
)
```

### 3. 获取已下载的引文 ID 列表

```python
from service.citations_service import get_downloaded_citation_ids

ids = get_downloaded_citation_ids(paper_id=1)
# [1, 2, 3, 5]  # download_status 为 success 或 exists 的 citation_id
```

---

## 快速选择

| 需求 | 推荐 |
|------|------|
| 直接读表，不做权限校验 | `CitationModel.get_citations_by_paper()` |
| 读表并校验论文归属 | `get_citations_for_paper(paper_id, user_id=...)` |
| 更新任意字段 | `CitationModel.update_citation()` |
| 仅更新下载/分析状态 | `update_citation_status()` |
| 获取已下载引文 ID | `get_downloaded_citation_ids()` |
