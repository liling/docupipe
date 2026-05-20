from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from dotenv import load_dotenv

from docupipe.destinations import DESTINATIONS
from docupipe.runner import run_pipeline_from_config
from docupipe.sources import SOURCES

load_dotenv()


def _setup_logging(level: str):
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--state-dir", default="./.state", help="状态文件目录")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              help="日志级别")
@click.pass_context
def main(ctx, state_dir, log_level):
    _setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["state_dir"] = Path(state_dir)


@main.command()
@click.option("--config", "config_path", default="docupipe.yaml", help="配置文件路径")
@click.option("--pipeline", "pipeline_name", default=None, help="配置文件中的 pipeline 名称")
@click.option("--mode", type=click.Choice(["full", "incremental", "mirror"]), default=None,
              help="运行模式（覆盖配置）")
@click.option("--resume", is_flag=True, default=False, help="full 模式下断点续传")
@click.option("--change-detection", type=click.Choice(["mtime", "hash"]), default=None,
              help="mirror 模式的变更检测策略（覆盖配置）")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def run(ctx, config_path, pipeline_name, mode, resume, change_detection, dry_run):
    try:
        run_pipeline_from_config(
            config_path=config_path,
            state_dir=ctx.obj["state_dir"],
            pipeline_name=pipeline_name,
            cli_mode=mode,
            cli_resume=resume,
            cli_change_detection=change_detection,
            dry_run=dry_run,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@main.command("sources")
def list_sources():
    """列出可用的 Source"""
    for name in SOURCES:
        click.echo(f"  {name}")


@main.command("destinations")
def list_destinations():
    """列出可用的 Destination"""
    for name in DESTINATIONS:
        click.echo(f"  {name}")
