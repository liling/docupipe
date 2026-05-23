from __future__ import annotations

import logging
from pathlib import Path

import yaml

from docupipe.config import deep_merge, execute_variables_script, parse_component_config, resolve_env_vars
from docupipe.destinations import get_destination
from docupipe.display import Display
from docupipe.pipeline import Pipeline
from docupipe.plugins import load_config_plugins
from docupipe.sources import get_source
from docupipe.steps import get_step

logger = logging.getLogger(__name__)


def run_pipeline_from_config(
    config_path: str,
    state_dir: Path,
    pipeline_name: str | None = None,
    cli_mode: str | None = None,
    cli_resume: bool = False,
    cli_change_detection: str | None = None,
    dry_run: bool = False,
) -> None:
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    variables = execute_variables_script(raw)
    config = resolve_env_vars(raw, variables)

    global_config = {k: v for k, v in config.items() if k not in ("pipelines", "variables")}
    plugin_dirs = global_config.pop("plugin_dirs", [])
    if plugin_dirs:
        load_config_plugins(plugin_dirs)
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            raise ValueError(f"未找到 pipeline: {pipeline_name}")

    def _load_steps(specs, global_config, extension_rules):
        steps = []
        for spec in specs:
            if isinstance(spec, str):
                name = spec
                kwargs = {}
            else:
                items = list(spec.items())
                name, kwargs = items[0] if items else ("", {})
            global_step_config = global_config.get(name, {})
            if global_step_config:
                kwargs = deep_merge(global_step_config, kwargs)
            if name == "convert":
                kwargs["extension_rules"] = extension_rules
            step_cls = get_step(name)
            steps.append(step_cls(**kwargs))
        return steps

    for pipe_config in pipelines:
        source_name, source_kwargs = parse_component_config(pipe_config, global_config, "source")
        source = get_source(source_name)(**source_kwargs)

        dest_name, dest_kwargs = parse_component_config(pipe_config, global_config, "destination")
        dest = get_destination(dest_name)(**dest_kwargs)

        steps = _load_steps(pipe_config.get("steps", []), global_config, extension_rules)
        post_steps = _load_steps(pipe_config.get("post_steps", []), global_config, extension_rules)
        finalize_steps = _load_steps(pipe_config.get("finalize_steps", []), global_config, extension_rules)

        pipe_name = pipe_config.get("name", "")
        effective_mode = cli_mode or pipe_config.get("mode", "full")
        effective_cd = cli_change_detection or pipe_config.get("change_detection")
        options = pipe_config.get("options", {})

        try:
            pipeline = Pipeline(
                source, dest, state_dir,
                pipeline_name=pipe_name,
                display=Display(),
                steps=steps,
                post_steps=post_steps,
                finalize_steps=finalize_steps,
                state_file=pipe_config.get("state_file"),
                mode=effective_mode,
                change_detection=effective_cd,
                mirror_delete=options.get("mirror_delete", True),
            )
            pipeline.run(
                resume=cli_resume,
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()
            if hasattr(source, "close"):
                source.close()
