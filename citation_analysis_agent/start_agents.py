#!/usr/bin/env python3
"""
启动文件：用于运行多智能体协作分析
"""
import argparse
import logging
import sys
from pathlib import Path
import dotenv
import os
dotenv.load_dotenv()
# 添加路径以便导入agent（start_agents.py 在 ciation_analysis_agent 目录下）
sys.path.insert(0, str(Path(__file__).parent))

from agent.workflows import run_minimal_analysis, run_supervisor_analysis


def setup_logging(verbose: bool = False):
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

def run_analysis(
    paper_id: str,
    citation_ids=None,
    original_paper_path=None,
    write_output: bool = True,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    verbose: bool = False,
):
    # 配置日志
    setup_logging(verbose=verbose)

    # 设置环境变量
    import os
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url
    if model:
        os.environ["OPENAI_MODEL"] = model

    try:
        print("=" * 60)
        print("运行 Supervisor Agent 模式分析...")
        print("=" * 60)
        print("Supervisor Agent 将自主决定如何协调多个子 agents 进行分析")
        print("=" * 60)

        result = run_supervisor_analysis(
            paper_id=paper_id,
            citation_ids=citation_ids,
            original_paper_path=original_paper_path,
            write_output=write_output,
        )

        print("\n" + "=" * 60)
        print("Supervisor Agent 分析完成")
        print("=" * 60)

        return result

    except Exception as e:
        print(f"\nSupervisor Agent 分析失败: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(
        description="运行多智能体协作分析（引用分析 + 情感分析）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行协作分析（默认模式）
  python start_agents.py papers/MyPaper
  
  # 指定特定的引用ID
  python start_agents.py papers/MyPaper --citations 1 2 3
  
  # 指定原论文路径（用于章节映射）
  python start_agents.py papers/MyPaper --primary papers/MyPaper/original.pdf
        """,
    )
    parser.add_argument("paper_id", type=str, help="论文目录路径")
    parser.add_argument(
        "--citations",
        type=int,
        nargs="*",
        help="可选：指定要分析的引用ID列表",
    )
    parser.add_argument(
        "--primary",
        type=str,
        help="可选：原论文路径（txt或pdf），用于章节映射",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="跳过写入报告文件",
    )
    parser.add_argument("--api-key", type=str, help="覆盖LLM API key")
    parser.add_argument("--base-url", type=str, help="覆盖LLM base URL")
    parser.add_argument("--model", type=str, help="覆盖LLM model名称")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志（DEBUG级别）",
    )
    
    args = parser.parse_args()
    
    # 配置日志
    setup_logging(verbose=args.verbose)

    # 设置环境变量（如果提供了参数）
    import os
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url
    if args.model:
        os.environ["OPENAI_MODEL"] = args.model

    # 运行 Supervisor Agent 模式分析
    try:
        print("=" * 60)
        print("运行 Supervisor Agent 模式分析...")
        print("=" * 60)
        print("Supervisor Agent 将自主决定如何协调多个子 agents 进行分析")
        print("=" * 60)
        
        result = run_minimal_analysis(
            paper_id=args.paper_id,
            citation_ids=args.citations,
            original_paper_path=args.primary,
            write_output=not args.no_write,
        )
        
        print("\n" + "=" * 60)
        print("Supervisor Agent 分析完成")
        print("=" * 60)
        
        return result
    except Exception as e:
        print(f"\nSupervisor Agent 分析失败: {e}")
        raise


if __name__ == "__main__":
    run_analysis('storage\papers\\1\citations')
#     os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
#     # print(os.environ["OPENAI_API_KEY"])
#     result = run_supervisor_analysis(
#     paper_id="storage/papers/1/citations",
# )
    # print(result)

