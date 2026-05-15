from __future__ import annotations

import os
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


@click.group()
@click.option("--state-dir", default="./.state", help="状态文件目录")
@click.pass_context
def main(ctx, state_dir):
    """通用文档传输 pipeline"""
    ctx.ensure_object(dict)
    ctx.obj["state_dir"] = Path(state_dir)


@main.command()
@click.option("--source", "source_name", required=True, help="Source 名称")
@click.option("--dest", "dest_name", required=True, help="Destination 名称")
@click.option("--config", "config_path", default=None, help="配置文件路径")
@click.option("--pipeline", "pipeline_name", default=None, help="配置文件中的 pipeline 名称")
@click.option("--resume", is_flag=True, default=False, help="跳过已处理的文档")
@click.option("--sync", "sync_mode", is_flag=True, default=False, help="仅同步有变化的文档")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.option("--space", default=None, help="钉钉知识库 ID")
@click.option("--folder", default=None, help="钉钉文件夹 ID")
@click.option("--input-dir", default=None, help="本地文件夹路径")
@click.option("--bank-id", default=None, help="Hindsight Bank ID")
@click.option("--hindsight-url", default=None, help="Hindsight API URL")
@click.option("--hindsight-key", default=None, help="Hindsight API Key")
@click.option("--context", default=None, help="Hindsight context 前缀")
@click.pass_context
def run(ctx, source_name, dest_name, config_path, pipeline_name, resume, sync_mode, dry_run,
        space, folder, input_dir, bank_id, hindsight_url, hindsight_key, context):
    """运行文档传输 pipeline"""
    if config_path:
        _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run)
    else:
        _run_single(ctx, source_name, dest_name, resume, sync_mode, dry_run,
                     space=space, folder=folder, input_dir=input_dir,
                     bank_id=bank_id, hindsight_url=hindsight_url,
                     hindsight_key=hindsight_key, context=context)


def _run_single(ctx, source_name, dest_name, resume, sync_mode, dry_run, **kwargs):
    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source

    source_cls = get_source(source_name)
    dest_cls = get_destination(dest_name)

    source_config = _extract_source_config(source_name, kwargs)
    dest_config = _extract_dest_config(dest_name, kwargs)

    source = source_cls(**source_config)
    dest = dest_cls(**dest_config)

    try:
        pipeline = Pipeline(source, dest, ctx.obj["state_dir"], display=Display())
        pipeline.run(resume=resume, sync=sync_mode, dry_run=dry_run)
    finally:
        if hasattr(dest, "close"):
            dest.close()


def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name = pipe_config["source"]
        dest_name = pipe_config["destination"]
        options = pipe_config.get("options", {})
        source_config = pipe_config.get("source_config", {})
        dest_config = pipe_config.get("dest_config", {})

        source_cls = get_source(source_name)
        dest_cls = get_destination(dest_name)

        source = source_cls(**source_config)
        dest = dest_cls(**dest_config)

        try:
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"], display=Display())
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()


def _extract_source_config(source_name, kwargs):
    config = {}
    if source_name == "dingtalk":
        if kwargs.get("space"):
            config["space_id"] = kwargs["space"]
        if kwargs.get("folder"):
            config["folder_id"] = kwargs["folder"]
    elif source_name == "local":
        if kwargs.get("input_dir"):
            config["input_dir"] = kwargs["input_dir"]
    return config


def _extract_dest_config(dest_name, kwargs):
    config = {}
    if dest_name == "hindsight":
        if kwargs.get("bank_id"):
            config["bank_id"] = kwargs["bank_id"]
        if kwargs.get("hindsight_url"):
            config["api_url"] = kwargs["hindsight_url"]
        if kwargs.get("hindsight_key"):
            config["api_key"] = kwargs["hindsight_key"]
        if kwargs.get("context"):
            config["context_prefix"] = kwargs["context"]
    return config


@main.command("sources")
def list_sources():
    """列出可用的 Source"""
    from docpipe.sources import SOURCES
    for name, cls in SOURCES.items():
        click.echo(f"  {name}")


@main.command("destinations")
def list_destinations():
    """列出可用的 Destination"""
    from docpipe.destinations import DESTINATIONS
    for name, cls in DESTINATIONS.items():
        click.echo(f"  {name}")
