from __future__ import annotations

import os
from pathlib import Path

import click
from dotenv import load_dotenv

# 自动加载 .env 文件
load_dotenv()


@click.group()
@click.option("--output", "output_dir", default="./output", help="输出目录")
@click.pass_context
def main(ctx, output_dir):
    """钉钉知识库下载并同步到 Hindsight"""
    ctx.ensure_object(dict)
    ctx.obj["output_dir"] = output_dir


@main.command()
@click.option("--space", required=True, help="知识库 ID")
@click.option("--folder", default=None, help="指定文件夹 ID，不传则从根目录开始")
@click.option("--resume", is_flag=True, default=False, help="跳过已下载的文档")
@click.pass_context
def download(ctx, space, folder, resume):
    """从钉钉知识库下载内容并保存为 Markdown"""
    output_dir = Path(ctx.obj["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    from dwsdocs_downloader.display import Display
    from dwsdocs_downloader.wiki_client import WikiClient
    from dwsdocs_downloader.downloader import Downloader

    display = Display()
    client = WikiClient()
    dl = Downloader(client, output_dir, display=display)
    dl.download(space_id=space, folder_id=folder, resume=resume)


@main.command()
@click.option("--bank-id", default=None, help="Hindsight Bank ID")
@click.option("--hindsight-url", default=None, help="Hindsight API URL")
@click.option("--hindsight-key", default=None, help="Hindsight API Key")
@click.option("--context", default=None, help="Hindsight context 前缀")
@click.option("--resume", is_flag=True, default=False, help="跳过已上传的文档")
@click.option("--sync", "sync_mode", is_flag=True, default=False, help="仅同步有变化的文档")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def retain(ctx, bank_id, hindsight_url, hindsight_key, context, resume, sync_mode, dry_run):
    """将本地 Markdown 文档同步到 Hindsight"""
    output_dir = Path(ctx.obj["output_dir"])
    bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
    hindsight_url = hindsight_url or os.environ.get("HINDSIGHT_API_URL", "")
    hindsight_key = hindsight_key or os.environ.get("HINDSIGHT_API_KEY", "")
    context = context or os.environ.get("HINDSIGHT_CONTEXT", "")

    if not hindsight_url or not bank_id:
        click.echo("错误：缺少 HINDSIGHT_API_URL 或 HINDSIGHT_BANK_ID")
        raise SystemExit(1)

    from hindsight_client import Hindsight

    from dwsdocs_downloader.display import Display
    from dwsdocs_downloader.retain import RetainRunner

    display = Display()
    runner = RetainRunner(output_dir, display=display)

    with Hindsight(base_url=hindsight_url, api_key=hindsight_key or None) as client:
        runner.run(client, bank_id, resume=resume, sync=sync_mode, dry_run=dry_run, context_prefix=context or None)
