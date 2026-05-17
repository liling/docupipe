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
@click.option("--config", "config_path", default="docupipe.yaml", help="配置文件路径")
@click.option("--pipeline", "pipeline_name", default=None, help="配置文件中的 pipeline 名称")
@click.option("--resume", is_flag=True, default=False, help="跳过已处理的文档")
@click.option("--sync", "sync_mode", is_flag=True, default=False, help="仅同步有变化的文档")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def run(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    """运行文档传输 pipeline"""
    _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run)


def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docupipe.config import deep_merge, execute_variables_script, parse_component_config, resolve_env_vars
    from docupipe.destinations import get_destination
    from docupipe.display import Display
    from docupipe.pipeline import Pipeline
    from docupipe.sources import get_source
    from docupipe.steps import get_step

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    variables = execute_variables_script(raw)
    config = resolve_env_vars(raw, variables)

    global_config = {k: v for k, v in config.items() if k not in ("pipelines", "variables")}
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name, source_kwargs = parse_component_config(pipe_config, global_config, "source")
        source = get_source(source_name)(**source_kwargs)

        dest_name, dest_kwargs = parse_component_config(pipe_config, global_config, "destination")
        dest = get_destination(dest_name)(**dest_kwargs)

        steps = []
        for step_spec in pipe_config.get("steps", []):
            if isinstance(step_spec, str):
                step_name = step_spec
                step_kwargs = {}
            else:
                items = list(step_spec.items())
                step_name, step_kwargs = items[0] if items else ("", {})

            global_step_config = global_config.get(step_name, {})
            if global_step_config:
                step_kwargs = deep_merge(global_step_config, step_kwargs)

            if step_name == "convert":
                step_kwargs["extension_rules"] = extension_rules

            step_cls = get_step(step_name)
            steps.append(step_cls(**step_kwargs))

        options = pipe_config.get("options", {})
        try:
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), steps=steps)
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()


@main.command("sources")
def list_sources():
    """列出可用的 Source"""
    from docupipe.sources import SOURCES
    for name, cls in SOURCES.items():
        click.echo(f"  {name}")


@main.command("destinations")
def list_destinations():
    """列出可用的 Destination"""
    from docupipe.destinations import DESTINATIONS
    for name, cls in DESTINATIONS.items():
        click.echo(f"  {name}")
