from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


def _setup_logging(level: str):
    """配置根日志级别"""
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
    """通用文档传输 pipeline"""
    _setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["state_dir"] = Path(state_dir)


@main.command()
@click.option("--source", "source_name", default=None, help="Source 名称")
@click.option("--dest", "dest_name", default=None, help="Destination 名称")
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
@click.option("--enable-image-description", is_flag=True, default=False,
              help="启用图片描述生成")
@click.option("--image-api-key", default=None, envvar="IMAGE_DESCRIPTION_API_KEY",
              help="图片描述 API Key")
@click.option("--image-base-url", default=None, envvar="IMAGE_DESCRIPTION_BASE_URL",
              help="图片描述 API Base URL")
@click.option("--image-model", default="gpt-4o", envvar="IMAGE_DESCRIPTION_MODEL",
              help="图片描述模型名称")
@click.pass_context
def run(ctx, source_name, dest_name, config_path, pipeline_name, resume, sync_mode, dry_run,
        space, folder, input_dir, bank_id, hindsight_url, hindsight_key, context,
        enable_image_description, image_api_key, image_base_url, image_model):
    """运行文档传输 pipeline"""
    if config_path:
        _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run)
    elif source_name and dest_name:
        _run_single(ctx, source_name, dest_name, resume, sync_mode, dry_run,
                     space=space, folder=folder, input_dir=input_dir,
                     bank_id=bank_id, hindsight_url=hindsight_url,
                     hindsight_key=hindsight_key, context=context,
                     image_description=enable_image_description,
                     image_description_api_key=image_api_key,
                     image_description_base_url=image_base_url,
                     image_description_model=image_model)
    else:
        click.echo("错误：需要 --source/--dest 或 --config")
        raise SystemExit(1)


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

    from docpipe.converters.resolver import TypeRuleResolver
    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))

    type_rules = config.get("type_rules", {})
    resolver = TypeRuleResolver(
        extension_rules=type_rules.get("extensions", {}),
        mime_rules=type_rules.get("mime_types", {}),
    )

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
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), type_resolver=resolver)
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
        if kwargs.get("image_description"):
            config["image_description"] = True
            config["image_description_api_key"] = kwargs.get("image_description_api_key", "")
            config["image_description_base_url"] = kwargs.get("image_description_base_url", "")
            config["image_description_model"] = kwargs.get("image_description_model", "gpt-4o")
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
