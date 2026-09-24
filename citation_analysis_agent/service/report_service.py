from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


from model.report_model import ReportModel


try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from agent.workflows import run_summarize
from weasyprint import HTML
try:
    from model.model import DatabaseModel
    from model.citation_model import CitationModel
except ImportError:
    from .model.model import DatabaseModel
    from .model.citation_model import CitationModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _get_shanghai_time_str() -> str:
    if ZoneInfo is None:
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y/%m/%d %H:%M:%S")


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _escape_html(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def setup_logging(verbose: bool = False) -> None:
    """配置日志格式"""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = (
        "%(asctime)s %(filename)s:%(lineno)d [%(levelname)8s] [%(name)s] %(message)s"
        if verbose
        else "%(asctime)s %(filename)s:%(lineno)d [%(levelname)8s] %(message)s"
    )
    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _extract_summary_text(summation: Any) -> str:
    if isinstance(summation, dict):
        for key in ("summary", "overview", "summarize"):
            value = summation.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(summation, str) and summation.strip():
        return summation.strip()
    return ""


def _resolve_paper_id_from_path(paper_path: str | Path) -> int | None:
    path = Path(paper_path)
    if path.name.isdigit():
        return int(path.name)
    if path.name == "citations" and path.parent.name.isdigit():
        return int(path.parent.name)
    if path.parent.name.isdigit():
        return int(path.parent.name)
    return None


def _load_cited_title(info_path: Path) -> str | None:
    paper_id = _resolve_paper_id_from_path(info_path.parent)
    db_path = os.getenv("CITATION_DB_PATH", "citation_analysis.db")
    db = DatabaseModel(db_path=db_path)
    try:
        if paper_id is not None:
            paper = db.get_paper(paper_id)
            if paper and paper.get("title"):
                return str(paper.get("title")).strip()
    finally:
        db.close()

    if not info_path.exists():
        return None
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            title = data.get("Title") or data.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
    except Exception:
        return None
    return None


def _build_font_config(font_path: str | None) -> tuple[str, str]:
    fallback_stack = (
        "'Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Micro Hei', "
        "'WenQuanYi Zen Hei', 'Microsoft YaHei', 'SimHei', sans-serif"
    )
    if not font_path:
        return "", fallback_stack

    font_file = Path(font_path)
    if not font_file.exists():
        logger.warning("指定字体文件不存在: %s", font_path)
        return "", fallback_stack

    font_uri = font_file.resolve().as_uri()
    font_css = (
        "@font-face {"
        "  font-family: 'CustomCJK';"
        f"  src: url('{font_uri}');"
        "  font-display: swap;"
        "}"
    )
    return font_css, "'CustomCJK', " + fallback_stack


def run_summarize_analysis(paper_id: str) -> dict[str, Any]:
    """
    对 multiprocess_analysis_report.json 中的所有结果进行总结。
    
    Args:
        paper_id: 论文目录路径（指向 citations 目录）
    
    Returns:
        包含总结结果的字典
    """
    report_path = Path(paper_id) / "multiprocess_analysis_report.json"

    # 读取已存在的分析报告
    all_results: list = []
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except Exception:
            all_results = []

    # 执行总结
    summation = run_summarize(all_results)
        
    return summation


def build_combined_markdown_report(
    groups: Iterable[dict[str, Any]],
    report_title: str = "联合分析报告",
    font_css: str = "",
    font_family: str = "",
) -> str:
    group_list = list(groups or [])
    safe_report_title = report_title.strip() if isinstance(report_title, str) and report_title.strip() else "联合分析报告"

    html: list[str] = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        "<meta charset=\"utf-8\" />",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        f"<title>{_escape_html(safe_report_title)}</title>",
        "<style>",
        f"  {font_css}",
        "  @page { size: A4; margin: 18mm 16mm; }",
        "  :root { --bg: #ffffff; --card: #f8fafc; --muted: #475569; --text: #0f172a; --accent: #2563eb; --border: #e2e8f0; }",
        "  * { box-sizing: border-box; }",
        f"  body {{ margin: 0; font-size: 13px; font-family: {font_family or "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"}; background: var(--bg); color: var(--text); }}",
        "  .container { max-width: 900px; margin: 0 auto; padding: 24px 12px 48px; }",
        "  .header { display: flex; flex-direction: column; gap: 6px; margin-bottom: 24px; }",
        "  .title { font-size: 22px; font-weight: 700; }",
        "  .meta { color: var(--muted); font-size: 12px; }",
        "  .section { margin-top: 24px; }",
        "  .section h2 { font-size: 16px; margin: 0 0 12px; }",
        "  .hint { color: var(--muted); font-size: 12px; font-weight: 400; }",
        "  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 16px; }",
        "  .overview-item { padding: 14px; border-radius: 12px; background: #ffffff; border: 1px solid var(--border); margin-bottom: 12px; }",
        "  .overview-title { color: var(--accent); font-weight: 600; text-decoration: none; }",
        "  .overview-text { margin-top: 8px; color: var(--text); line-height: 1.6; white-space: pre-wrap; }",
        "  .group-title { font-size: 15px; font-weight: 700; margin: 0 0 8px; }",
        "  .badge { display: inline-block; padding: 2px 10px; font-size: 12px; color: var(--muted); border: 1px solid var(--border); border-radius: 999px; margin-left: 8px; }",
        "  .task { margin-top: 12px; padding: 14px; border-radius: 12px; border: 1px dashed #cbd5f5; background: #ffffff; }",
        "  .task h4 { margin: 0 0 8px; font-size: 14px; }",
        "  .kv { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; }",
        "  .citations { margin-top: 10px; }",
        "  .citation { border-left: 2px solid #2563eb; padding-left: 12px; margin: 10px 0; }",
        "  .citation h5 { margin: 0 0 6px; font-size: 13px; color: #1e3a8a; }",
        "  pre { margin: 8px 0 0; padding: 10px; background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; color: #0f172a; white-space: pre-wrap; word-break: break-word; font-size: 12px; }",
        "  .divider { height: 1px; background: var(--border); margin: 16px 0; }",
        "  .footer { margin-top: 32px; color: var(--muted); font-size: 11px; text-align: center; }",
        "</style>",
        "</head>",
        "<body>",
        "<div class=\"container\">",
    ]

    html.extend(
        [
            "<div class=\"header\">",
            f"<div class=\"title\">{_escape_html(safe_report_title)}</div>",
            f"<div class=\"meta\">生成时间：{_escape_html(_get_shanghai_time_str())}</div>",
            f"<div class=\"meta\">包含被引论文数：{len(group_list)}</div>",
            "</div>",
        ]
    )

    if group_list:
        html.extend([
            "<div class=\"section\">",
            "<h2>概述 <span class=\"hint\">（点击标题跳转）</span></h2>",
        ])
        for group_index, group_data in enumerate(group_list):
            group = group_data if isinstance(group_data, dict) else {}
            cited_title = group.get("cited_title") or "未命名被引论文"
            overview = group.get("overview")
            anchor = f"cited-{group_index + 1}"
            html.append("<div class=\"overview-item\">")
            html.append(
                f"<a class=\"overview-title\" href=\"#{_escape_html(anchor)}\">{_escape_html(cited_title)}</a>"
            )
            if overview:
                html.append(f"<div class=\"overview-text\">{_escape_html(overview)}</div>")
            html.append("</div>")
        html.append("</div>")

    html.append("<div class=\"section\">")
    html.append("<h2>详细信息</h2>")

    for group_index, group_data in enumerate(group_list):
        group = group_data if isinstance(group_data, dict) else {}
        cited_title = group.get("cited_title") or "未命名被引论文"
        tasks_list = _safe_list(group.get("tasks"))
        anchor = f"cited-{group_index + 1}"
        html.append(f"<div class=\"card\" id=\"{_escape_html(anchor)}\">")
        html.append(
            f"<div class=\"group-title\">{group_index + 1}. {_escape_html(cited_title)}"
            f"<span class=\"badge\">引用数：{len(tasks_list)}</span>"
            f"<span class=\"badge\">已分析：{len([task for task in tasks_list if task.get('status') == 'analysised'])}</span></div>"
        )

        for task_index, task_data in enumerate(tasks_list):
            if task_data.get("status") != "analysised":
                continue
            task = task_data if isinstance(task_data, dict) else {}
            paper_title = task.get("paper") or "未命名论文"
            status = task.get("status")
            citations = _safe_list(task.get("citations"))

            html.append("<div class=\"task\">")
            html.append(
                f"<h4>{group_index + 1}.{task_index + 1} {_escape_html(paper_title)}</h4>"
            )
            kv_parts = []
            if status:
                kv_parts.append(f"状态：{_escape_html(status)}")
            kv_parts.append(f"引用数量：{len(citations)}")
            html.append(
                f"<div class=\"kv\">{' | '.join(kv_parts)}</div>"
            )

            if citations:
                html.append("<div class=\"citations\">")
                for index, citation in enumerate(citations):
                    citation = citation if isinstance(citation, dict) else {}
                    reference_number = citation.get("reference_number")
                    snippet_index = citation.get("snippet_index")
                    sentiment = citation.get("sentiment")
                    text = citation.get("text")
                    analysis = citation.get("analysis")

                    html.append("<div class=\"citation\">")
                    html.append(f"<h5>引用片段 {index + 1}</h5>")
                    if reference_number is not None:
                        html.append(f"<div class=\"kv\">引用编号：{_escape_html(reference_number)}</div>")
                    if snippet_index is not None:
                        html.append(f"<div class=\"kv\">片段编号：{_escape_html(snippet_index)}</div>")
                    if sentiment:
                        html.append(f"<div class=\"kv\">情感倾向：{_escape_html(sentiment)}</div>")
                    if text:
                        html.append("<pre><code>")
                        html.append(_escape_html(text))
                        html.append("</code></pre>")
                    if analysis:
                        html.append(f"<div class=\"overview-text\">{_escape_html(analysis)}</div>")
                    html.append("</div>")
                html.append("</div>")

            html.append("</div>")
        html.append("</div>")

    html.append("</div>")
    html.append("<div class=\"footer\">Generated by Citation Analysis Agent</div>")
    html.append("</div>")
    html.append("</body>")
    html.append("</html>")

    return "\n".join(html)


def generate_combined_report(
    inputs: Iterable[str | Path],
    output: str | Path = "report.html",
    report_title: str = "联合分析报告",
    font_path: str = "SourceHanSerifSC-VF.ttf",
) -> tuple[Path, Path]:
    groups: list[dict[str, Any]] = []
    for input_item in inputs:
        input_path = Path(input_item)
        if input_path.is_dir():
            report_path = input_path / "multiprocess_analysis_report.json"
            paper_dir = input_path
        else:
            report_path = input_path
            paper_dir = input_path.parent

        if report_path.name != "multiprocess_analysis_report.json":
            report_path = report_path / "multiprocess_analysis_report.json"

        tasks_data: list[dict[str, Any]] = []
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    tasks_data = json.load(f)
            except Exception:
                tasks_data = []

        cited_title = paper_dir.name
        if paper_dir.name == "citations" and paper_dir.parent.name:
            cited_title = paper_dir.parent.name

        info_path = paper_dir / "info.json"
        info_title = _load_cited_title(info_path)
        if info_title:
            cited_title = info_title

        overview_text = ""
        try:
            summation = run_summarize_analysis(str(paper_dir))
            overview_text = _extract_summary_text(summation)
        except Exception:
            overview_text = ""

        groups.append({
            "cited_title": cited_title,
            "overview": overview_text,
            "tasks": tasks_data,
        })

    font_css, resolved_font_family = _build_font_config(font_path)
    report = build_combined_markdown_report(
        groups,
        report_title=report_title,
        font_css=font_css,
        font_family=resolved_font_family,
    )
    output_path = Path(output)
    print(f"生成联合分析报告，保存到: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    pdf_path = output_path.with_suffix(".pdf")
    HTML(string=report, base_url=str(output_path.resolve().parent)).write_pdf(pdf_path)
    print(f"已生成 PDF 报告: {pdf_path}")
    return output_path, pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate combined markdown analysis report")
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Path(s) to multiprocess_analysis_report.json or citations directory",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="report.html",
        help="Output html file path (default: report.html)",
    )
    parser.add_argument("--api-key", type=str, help="覆盖LLM API key")
    parser.add_argument("--base-url", type=str, help="覆盖LLM base URL")
    parser.add_argument("--model", type=str, help="覆盖LLM model名称")
    parser.add_argument("--font-path", type=str, help="指定中文字体文件路径（ttf/otf/ttc）")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细日志（DEBUG级别）",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    import os

    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url
    if args.model:
        os.environ["OPENAI_MODEL"] = args.model

    generate_combined_report(
        inputs=args.inputs, # 需要生成联合报告的多个 citations 目录路径
        output=args.output, # 示例：storage/reports/报告名.html，html生成后会被转为pdf
        font_path=args.font_path, # 字体所在路径，服务器上为2/citation_analysis_agent/SourceHanSerifSC-VF.ttf
    )





DEFAULT_STORAGE_ROOT = "storage"
DEFAULT_FONT_PATH = "SourceHanSerifSC-VF.ttf"


def run_combined_report_task(
    report_id: int,
    user_id: int,
    paper_ids: List[int],
    *,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    font_path: Optional[str] = None,
) -> None:
    """
    后台任务：根据 paper_ids 生成联合报告，保存到 storage/report/user_id/report_id/，
    并更新 report 表的 status、html_path、pdf_path。
    """
    rm = ReportModel()
    try:
        rm.update_report(report_id, user_id=user_id, status="analysis")
        report_record = rm.get_report(report_id, user_id=user_id) or {}
        report_title = str(report_record.get("name") or "").strip() or "联合分析报告"

        base = Path(storage_root)
        inputs = [
            str(base / "papers" / str(pid) / "citations")
            for pid in paper_ids
        ]

        out_dir = base / "report" / str(user_id) / str(report_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_html = out_dir / f"{report_id}.html"

        font = font_path or DEFAULT_FONT_PATH
        if not Path(font).exists():
            font = None

        html_path, pdf_path = generate_combined_report(
            inputs=inputs,
            output=str(output_html),
            report_title=report_title,
            font_path=font or "",
        )

        abs_html = str(html_path.resolve())
        abs_pdf = str(pdf_path.resolve())

        rm.update_report(
            report_id,
            user_id=user_id,
            status="completed",
            html_path=abs_html,
            pdf_path=abs_pdf,
        )
        logger.info("Report %s completed: %s", report_id, abs_pdf)
    except Exception as e:
        logger.exception("Report %s failed: %s", report_id, e)
        rm.update_report(report_id, user_id=user_id, status="failed")


def add_report(
    user_id: int,
    name: str,
    paper_ids: Optional[List[int]] = None,
    paper_count: Optional[int] = None,
    status: Optional[str] = "pending",
    html_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
) -> int:
    """
    创建一条报告记录。
    若未传 paper_count，则根据 paper_ids 长度自动计算。
    """
    rm = ReportModel()
    ids = paper_ids if paper_ids is not None else []
    count = paper_count if paper_count is not None else len(ids)
    return rm.add_report(
        user_id=user_id,
        name=name,
        paper_ids=ids,
        paper_count=count,
        status=status or "pending",
        html_path=html_path,
        pdf_path=pdf_path,
    )


def get_report(
    report_id: int,
    *,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    获取单条报告。
    若传入 user_id，校验该报告属于该用户。
    """
    rm = ReportModel()
    return rm.get_report(report_id, user_id=user_id)


def list_reports(
    *,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    列出报告列表。
    若传入 user_id，仅返回该用户的报告。
    """
    rm = ReportModel()
    return rm.list_reports(user_id=user_id)


def update_report(
    report_id: int,
    *,
    name: Optional[str] = None,
    paper_ids: Optional[List[int]] = None,
    paper_count: Optional[int] = None,
    status: Optional[str] = None,
    html_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    user_id: Optional[int] = None,
) -> bool:
    """
    更新报告。仅更新传入的非 None 字段。
    若传入 user_id，校验该报告属于该用户。
    """
    rm = ReportModel()
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if paper_ids is not None:
        kwargs["paper_ids"] = paper_ids
    if paper_count is not None:
        kwargs["paper_count"] = paper_count
    if status is not None:
        kwargs["status"] = status
    if html_path is not None:
        kwargs["html_path"] = html_path
    if pdf_path is not None:
        kwargs["pdf_path"] = pdf_path
    if not kwargs:
        return False
    return rm.update_report(report_id, user_id=user_id, **kwargs)


def delete_report(
    report_id: int,
    *,
    user_id: Optional[int] = None,
) -> bool:
    """
    删除报告。
    若传入 user_id，校验该报告属于该用户。
    """
    rm = ReportModel()
    return rm.delete_report(report_id, user_id=user_id)
