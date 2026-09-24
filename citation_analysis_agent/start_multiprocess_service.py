"""
CLI 入口：多线程引文分析服务。
实际逻辑在 service.analysis_service，从数据库读取引文、分析完成后更新 analysis_status。
"""
import argparse
import logging
import os
import time

import dotenv

from service.analysis_service import (
    run_multithread_service,
    run_summarize_analysis,
)

dotenv.load_dotenv()


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


def main():
    parser = argparse.ArgumentParser(
        description="运行多线程服务：从数据库读取引文并进行分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行协作分析（默认模式）
  python start_multiprocess_service.py storage/papers/62/citations

  # 指定分析模式
  python start_multiprocess_service.py storage/papers/62/citations --mode agentic
        """,
    )
    parser.add_argument(
        "citations_dir",
        type=str,
        help="citations 目录路径，如 storage/papers/62/citations",
    )
    parser.add_argument(
        "--api-key", type=str, help="覆盖 LLM API key"
    )
    parser.add_argument("--base-url", type=str, help="覆盖 LLM base URL")
    parser.add_argument("--model", type=str, help="覆盖 LLM model 名称")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志（DEBUG 级别）",
    )
    parser.add_argument(
        "--mode",
        type=str,
        help="分析模式（minimal/agentic），默认 minimal",
        default="minimal",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="仅执行总结（读取 multiprocess_analysis_report.json 生成 summarize_report.json）",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url
    if args.model:
        os.environ["OPENAI_MODEL"] = args.model

    try:
        print("=" * 60)
        print("运行多线程引文分析服务...")
        print("=" * 60)
        start_time = time.time()

        if args.summarize:
            results = run_summarize_analysis(args.citations_dir)
            print("总结完成")
        else:
            results = run_multithread_service(
                citations_dir=args.citations_dir,
                mode=args.mode,
            )
            print(f"分析完成，共 {len(results)} 条引文")

        elapsed = time.time() - start_time
        print(f"耗时: {elapsed:.1f} 秒")
        print("=" * 60)
        return results
    except Exception as e:
        print(f"\n多线程服务失败: {e}")
        raise


if __name__ == "__main__":
    main()
