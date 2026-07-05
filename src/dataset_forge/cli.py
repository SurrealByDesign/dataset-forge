from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from dataset_forge import __version__
from dataset_forge.execution.default import build_default_pipeline
from dataset_forge.execution.pipeline import PipelineExecutionError
from dataset_forge.execution.state import load_state
from dataset_forge.pipeline import PipelineOptions, PipelineSummary, run_pipeline
from dataset_forge.presets import PresetError, list_presets, load_preset
from dataset_forge.plugins.registry import (
    PluginRegistry,
)
from dataset_forge.resources import ResourceLimitError, ResourceManager
from dataset_forge.cleanup import (
    ApprovalRequiredError,
    CleanupAction,
    CleanupOrchestrator,
    CleanupProfileError,
    ExecutionSummary,
    PlanControlError,
    PlanControlManager,
    SelectionFilter,
    execute_plan,
    load_cleanup_profile,
    load_cleanup_rules,
    parse_filter,
    review_plan,
)
from dataset_forge.cleanup.controls import OVERRIDES_JSON
from dataset_forge.cleanup.execute import TRANSFORMS
from dataset_forge.cleanup.io import load_cleanup_plan, write_cleanup_plan
from dataset_forge.core.structured import load_structured_file
from dataset_forge.discovery import discover_images
from dataset_forge.analysis.texture import generate_texture_report
from dataset_forge.analysis.health import generate_health_report
from dataset_forge.inspect import run_inspect


_FUTURE_COMMANDS = {
    "run",
    "resume",
    "simulate",
    "plugins",
    "texture-report",
    "health-report",
    "plan",
    "summarize-plan",
    "explain",
    "override",
    "lock",
    "unlock",
    "approve",
    "reject",
    "approve-all",
    "reset-overrides",
    "show-overrides",
    "review-plan",
    "execute-plan",
    "traditional-cleanup",
}


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataset-forge",
        description=(
            "Dataset Forge v0.8.0-alpha: inspect image datasets and write "
            "evidence-backed, read-only reports."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"dataset-forge {_package_version()}",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    inspect_parser = commands.add_parser(
        "inspect",
        help="Inspect an image dataset without modifying source images.",
    )
    inspect_parser.add_argument("dataset", type=Path, help="Dataset folder to inspect.")
    inspect_parser.add_argument(
        "--output", type=Path, default=None,
        help="Output folder for reports. Default: <dataset>/inspect_output/",
    )
    inspect_parser.add_argument(
        "--recursive", action="store_true", default=False,
        help="Scan sub-folders recursively.",
    )
    inspect_parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of images to analyze.",
    )
    inspect_parser.add_argument(
        "--gallery", action="store_true", default=False,
        help="Generate inspection_gallery.png for visual review of findings.",
    )
    return parser


def _package_version() -> str:
    return __version__


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not arguments:
        parser.print_help()
        return 0
    if arguments[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    if arguments[0] == "--version":
        print(f"dataset-forge {_package_version()}")
        return 0
    if arguments[0] == "inspect":
        try:
            return _inspect_main(arguments)
        except SystemExit as exc:
            return int(exc.code or 0)
    if arguments[0] in _FUTURE_COMMANDS or arguments[0].startswith("--"):
        print(
            "Error: this command is not part of the public v0.8.0-alpha CLI. "
            "Use 'dataset-forge inspect', '--help', or '--version'.",
            file=sys.stderr,
        )
        return 2
    print(f"Error: unknown command: {arguments[0]}", file=sys.stderr)
    return 2


def build_future_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataset-forge",
        description=(
            "Dataset Forge: Build better datasets. Prepare, analyze, clean, "
            "validate, benchmark, and export generative AI datasets."
        ),
    )
    parser.add_argument("--input", type=Path, help="Source image folder.")
    parser.add_argument("--output", type=Path, help="Generated output folder.")
    parser.add_argument("--recursive", type=parse_bool, default=False, metavar="true|false")
    parser.add_argument("--limit", type=int, help="Maximum number of supported images to scan.")
    parser.add_argument("--dry-run", action="store_true", help="Show writes without creating files.")
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Calculate quality metrics, duplicate groups, and dataset_report.json.",
    )
    parser.add_argument(
        "--health-report",
        action="store_true",
        help="Score dataset health and write image-level recommendations.",
    )
    parser.add_argument(
        "--quality-config",
        type=Path,
        help="Custom JSON file containing image and dataset scoring weights.",
    )
    parser.add_argument(
        "--review-gallery",
        action="store_true",
        help="Generate an offline HTML gallery for visual dataset review.",
    )
    parser.add_argument(
        "--thumbnail-size",
        type=int,
        default=256,
        help="Maximum thumbnail width and height in pixels. Default: 256.",
    )
    parser.add_argument(
        "--no-thumbnails",
        action="store_true",
        help="Reference original image paths instead of creating thumbnails.",
    )
    parser.add_argument(
        "--preset",
        help="Preset JSON path or a preset name from the presets folder.",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit.",
    )
    return parser


def future_main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"run", "resume", "simulate"}:
        return _pipeline_main(arguments)
    if arguments and arguments[0] == "plugins":
        return _plugins_main(arguments)
    if arguments and arguments[0] == "inspect":
        return _inspect_main(arguments)
    if arguments and arguments[0] == "texture-report":
        return _texture_main(arguments)
    if arguments and arguments[0] == "health-report":
        return _health_main(arguments)
    if arguments and arguments[0] in {
        "plan",
        "summarize-plan",
        "explain",
        "override",
        "lock",
        "unlock",
        "approve",
        "reject",
        "approve-all",
        "reset-overrides",
        "show-overrides",
        "review-plan",
        "execute-plan",
        "traditional-cleanup",
    }:
        return _cleanup_main(arguments)
    parser = build_future_parser()
    args = parser.parse_args(arguments)
    try:
        if args.list_presets:
            _print_presets()
            return 0
        if args.input is None or args.output is None:
            parser.error("--input and --output are required unless --list-presets is used")
        preset = load_preset(args.preset) if args.preset else None
        analyze = args.analyze or args.health_report or args.review_gallery
        summary = run_pipeline(
            PipelineOptions(
                input_path=args.input,
                output_path=args.output,
                recursive=args.recursive,
                limit=args.limit,
                dry_run=args.dry_run,
                analyze=analyze,
                health_report=args.health_report or args.review_gallery,
                quality_config=args.quality_config,
                review_gallery=args.review_gallery,
                thumbnail_size=args.thumbnail_size,
                no_thumbnails=args.no_thumbnails,
                preset=preset,
            )
        )
    except (OSError, PresetError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2

    _print_summary(summary)
    return 0 if summary.errors == 0 else 1


def _pipeline_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge",
        description="Dataset Forge: Build better datasets through modular pipelines.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Execute a registered pipeline.")
    run_parser.add_argument("--pipeline", default="default")
    run_parser.add_argument("--input", type=Path, default=Path("."))
    run_parser.add_argument("--output", type=Path, default=Path("output"))
    run_parser.add_argument("--recursive", type=parse_bool, default=False)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--preset")
    run_parser.add_argument("--quality-config", type=Path)
    run_parser.add_argument("--thumbnail-size", type=int, default=256)
    run_parser.add_argument("--no-thumbnails", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--force-stage")
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass resource safety limits.",
    )
    _add_resource_arguments(run_parser)

    resume_parser = commands.add_parser(
        "resume",
        help="Resume from output/pipeline_state.json.",
    )
    resume_parser.add_argument("--output", type=Path, default=Path("output"))
    resume_parser.add_argument("--force-stage")
    resume_parser.add_argument("--force", action="store_true")

    simulate_parser = commands.add_parser(
        "simulate",
        help="Preview a pipeline and resource plan without writing files.",
    )
    simulate_parser.add_argument("--pipeline", default="default")
    simulate_parser.add_argument("--input", type=Path, default=Path("."))
    simulate_parser.add_argument("--output", type=Path, default=Path("output"))
    simulate_parser.add_argument("--recursive", type=parse_bool, default=False)
    simulate_parser.add_argument("--limit", type=int)
    simulate_parser.add_argument("--preset")
    simulate_parser.add_argument("--quality-config", type=Path)
    simulate_parser.add_argument("--thumbnail-size", type=int, default=256)
    simulate_parser.add_argument("--no-thumbnails", action="store_true")
    simulate_parser.add_argument("--force-stage")
    _add_resource_arguments(simulate_parser)
    args = parser.parse_args(argv)
    try:
        if args.command in {"run", "simulate"}:
            if args.pipeline != "default":
                raise ValueError(f"Unknown pipeline: {args.pipeline}")
            preset = load_preset(args.preset) if args.preset else None
            resource_manager = _resource_manager_from_args(args)
            pipeline = build_default_pipeline(
                {
                    "recursive": args.recursive,
                    "limit": args.limit,
                    "quality_config": (
                        str(args.quality_config.expanduser().resolve())
                        if args.quality_config
                        else None
                    ),
                    "thumbnail_size": args.thumbnail_size,
                    "no_thumbnails": args.no_thumbnails,
                }
            )
            summary = pipeline.run(
                args.input,
                args.output,
                preset=preset,
                dry_run=args.command == "simulate" or args.dry_run,
                force_stage=args.force_stage,
                resource_manager=resource_manager,
                force=getattr(args, "force", False),
            )
        else:
            state = load_state(args.output.expanduser().resolve())
            if state.get("pipeline") != "default":
                raise ValueError(
                    f"Unknown pipeline in saved state: {state.get('pipeline')}"
                )
            pipeline = build_default_pipeline(dict(state.get("pipeline_config", {})))
            summary = pipeline.resume(
                args.output,
                force_stage=args.force_stage,
                force=args.force,
            )
    except (
        OSError,
        PipelineExecutionError,
        PresetError,
        ResourceLimitError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}")
        return 2

    if args.command == "simulate":
        print("\nSimulation complete. No files were written.")
    elif summary.status == "dry-run":
        print("\nDry run complete. No files were written.")
    else:
        print(f"Stages run: {summary.stages_run}")
        print(f"Stages skipped: {summary.stages_skipped}")
        print(f"Pipeline report: {summary.report_path}")
    return 0


def _inspect_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge inspect",
        description=(
            "Read an image dataset and write evidence-backed inspection reports.\n"
            "v0.8.0-alpha is analysis only: recommendations are advisory review priorities.\n"
            "Pipeline: Dataset -> DatasetContext -> Analyzer -> Finding -> Report"
        ),
    )
    parser.add_argument("dataset", type=Path, help="Dataset folder to inspect.")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output folder for reports. Default: <dataset>/inspect_output/",
    )
    parser.add_argument(
        "--recursive", action="store_true", default=False,
        help="Scan sub-folders recursively.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of images to analyze.",
    )
    parser.add_argument(
        "--gallery", action="store_true", default=False,
        help="Generate inspection_gallery.png for visual review of findings.",
    )
    args = parser.parse_args(argv[1:])

    dataset_path = args.dataset.expanduser().resolve()
    output_dir = (
        args.output.expanduser().resolve()
        if args.output
        else dataset_path / "inspect_output"
    )

    print("Dataset Forge Inspect")
    print("=====================")
    print(f"Dataset:  {dataset_path}")
    print(f"Output:   {output_dir}")
    print()

    try:
        result = run_inspect(
            dataset_path,
            output_dir,
            recursive=args.recursive,
            limit=args.limit,
            gallery=args.gallery,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2
    except OSError as exc:
        print(f"Error: {exc}")
        return 2

    # Summary - matches CLI_OUTPUT.md format
    print(f"Images:   {result.image_count}")
    print(f"Analyzed: {result.analyzed_count}")
    print(f"Errors:   {result.error_count}")
    print()
    print("Summary")
    print("-------")
    print(f"Total findings:  {result.total_findings}")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        count = result.severity_counts.get(sev, 0)
        if count:
            print(f"  {sev} severity:  {count}")
    print()
    print(f"Images with findings:  {result.images_with_findings} / {result.image_count}")
    print(f"Images with no issues: {result.images_clean} / {result.image_count}")
    print()
    if result.images_clean == result.image_count:
        print("All images are within normal parameters. No action recommended.")
    else:
        print(
            f"{result.images_clean} images require no action.\n"
            f"{result.images_with_findings} images have findings. "
            "Review report for details."
        )
    print()
    print("Recommendation Summary")
    print("----------------------")
    print(f"  Ready for Training: {result.ready_for_training_count}")
    print(f"  Needs Review:       {result.needs_review_count}")
    print(f"  Priority Review:    {result.priority_review_count}")
    print()
    print("Recommendations are advisory and based only on existing findings.")
    print("Source images were not modified.")
    print()
    print("Report written:")
    print(f"  {result.json_report}")
    print(f"  {result.txt_report}")
    print(f"  {result.recommendation_json}")
    print(f"  {result.recommendation_markdown}")
    if result.gallery_path:
        print(f"  {result.gallery_path}")
    return 0


def _texture_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge texture-report",
        description="Evaluate texture normalization needs without changing images.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recursive", type=parse_bool, default=False)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--thumbnail-size", type=int, default=256)
    parser.add_argument("--no-thumbnails", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        summary = generate_texture_report(
            args.input,
            args.output,
            recursive=args.recursive,
            limit=args.limit,
            thumbnail_size=args.thumbnail_size,
            create_thumbnails=not args.no_thumbnails,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
    print(f"Images analyzed: {summary.analyzed_images}")
    print(
        "Average microtexture density: "
        f"{summary.average_microtexture_density:.2f}"
    )
    print(f"Most over-textured: {summary.most_over_textured or 'none'}")
    print(f"Most representative: {summary.most_representative or 'none'}")
    print(f"Cleanest: {summary.cleanest or 'none'}")
    print(f"Texture report: {args.output.expanduser().resolve() / 'texture_report.html'}")
    return 0


def _health_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge health-report",
        description=(
            "Generate a Dataset Health Report from texture analysis output. "
            "Answers: 'How ready is this dataset for LoRA training, and what "
            "should I do before I train?'"
        ),
    )
    parser.add_argument("--input", type=Path, required=True,
        help="Source image folder (same as used for texture-report).")
    parser.add_argument("--output", type=Path, required=True,
        help="Output folder (may be the same as texture-report output).")
    parser.add_argument("--recursive", type=parse_bool, default=False)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-thumbnails", action="store_true")
    parser.add_argument("--duplicate-count", type=int, default=0,
        help="Number of exact duplicate images (from manifest pipeline).")
    parser.add_argument("--near-duplicate-count", type=int, default=0,
        help="Number of near-duplicate pairs.")
    args = parser.parse_args(argv[1:])
    try:
        # Run texture analysis first (required input for the health report)
        summary = generate_texture_report(
            args.input,
            args.output,
            recursive=args.recursive,
            limit=args.limit,
            create_thumbnails=not args.no_thumbnails,
        )
        # Load the results back from the CSV so health report uses all fields
        import csv as _csv
        results_path = args.output.expanduser().resolve() / "texture_report.csv"
        from dataset_forge.analysis.texture import TextureImageResult
        results = []
        with results_path.open(encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                results.append(TextureImageResult(
                    filename=row["filename"],
                    original_path=row["original_path"],
                    status=row["status"],
                    error=row.get("error", ""),
                    microtexture_density_score=float(row.get("microtexture_density_score", 0)),
                    local_contrast_score=float(row.get("local_contrast_score", 0)),
                    edge_sharpness_score=float(row.get("edge_sharpness_score", 0)),
                    highlight_speck_score=float(row.get("highlight_speck_score", 0)),
                    texture_consistency_score=float(row.get("texture_consistency_score", 0)),
                    watercolor_smoothness_score=float(row.get("watercolor_smoothness_score", 0)),
                    pencil_grain_score=float(row.get("pencil_grain_score", 0)),
                    representative_score=float(row.get("representative_score", 0)),
                    cleanliness_score=float(row.get("cleanliness_score", 0)),
                    texture_delta_from_average=float(row.get("texture_delta_from_average", 0)),
                    recommendation=row.get("recommendation", ""),
                    explanation=row.get("explanation", ""),
                    engine_recommendation=row.get("engine_recommendation", ""),
                    engine_confidence=int(row.get("engine_confidence", 0)),
                    engine_deciding_factor=row.get("engine_deciding_factor", ""),
                    engine_explanation=row.get("engine_explanation", ""),
                ))
        report = generate_health_report(
            results,
            summary,
            args.output.expanduser().resolve(),
            duplicate_count=args.duplicate_count,
            near_duplicate_count=args.near_duplicate_count,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
    print(f"Dataset Health:          {report.dataset_health_score:.0f}/100")
    print(f"Estimated LoRA Readiness:{report.lora_readiness_score:4d}/100")
    print(f"Headline: {report.headline}")
    print("Recommendations:")
    for rec in report.recommendations:
        print(f"  * {rec}")
    out = args.output.expanduser().resolve()
    print(f"Health report: {out / 'dataset_health_report.html'}")
    return 0


def _cleanup_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge",
        description="Dataset Forge: create and inspect explainable cleanup plans.",
    )
    commands = parser.add_subparsers(dest="cleanup_command", required=True)
    plan_parser = commands.add_parser("plan", help="Generate a CleanupPlan.")
    plan_parser.add_argument("--output", type=Path, default=Path("output"))
    plan_parser.add_argument("--manifest", type=Path)
    plan_parser.add_argument("--rules", type=Path)
    plan_parser.add_argument("--config", type=Path)
    plan_parser.add_argument("--profile", default="balanced")
    plan_parser.add_argument("--profile-config", type=Path)
    summary_parser = commands.add_parser(
        "summarize-plan",
        help="Summarize output/cleanup_plan.json.",
    )
    summary_parser.add_argument("--output", type=Path, default=Path("output"))
    explain_parser = commands.add_parser(
        "explain",
        help="Explain one planned image decision.",
    )
    explain_parser.add_argument("image")
    explain_parser.add_argument("--output", type=Path, default=Path("output"))
    override_parser = commands.add_parser(
        "override",
        help="Override one or more planned actions.",
    )
    override_parser.add_argument("image", nargs="?")
    override_parser.add_argument("--action", choices=[item.value for item in CleanupAction], required=True)
    _add_control_arguments(override_parser, where=True)
    lock_parser = commands.add_parser(
        "lock",
        help="Lock one or more effective decisions.",
    )
    lock_parser.add_argument("image", nargs="?")
    lock_parser.add_argument("--action", choices=[item.value for item in CleanupAction])
    _add_control_arguments(lock_parser, where=True)
    unlock_parser = commands.add_parser("unlock", help="Unlock an image decision.")
    unlock_parser.add_argument("image")
    _add_control_arguments(unlock_parser)
    approve_parser = commands.add_parser(
        "approve",
        help="Approve one or more effective decisions.",
    )
    approve_parser.add_argument("image", nargs="?")
    approve_parser.add_argument("--severity")
    _add_control_arguments(approve_parser, where=True)
    reject_parser = commands.add_parser(
        "reject",
        help="Reject one or more effective decisions.",
    )
    reject_parser.add_argument("image", nargs="?")
    _add_control_arguments(reject_parser, where=True)
    approve_all_parser = commands.add_parser(
        "approve-all",
        help="Approve every decision in the plan.",
    )
    _add_control_arguments(approve_all_parser)
    reset_parser = commands.add_parser(
        "reset-overrides",
        help="Clear saved overrides, locks, and approvals.",
    )
    _add_control_arguments(reset_parser)
    show_parser = commands.add_parser(
        "show-overrides",
        help="Display saved user controls.",
    )
    show_parser.add_argument("--output", type=Path, default=Path("output"))
    review_parser = commands.add_parser(
        "review-plan",
        help="Interactively review cleanup decisions.",
    )
    review_parser.add_argument("--output", type=Path, default=Path("output"))
    execute_parser = commands.add_parser(
        "execute-plan",
        help="Process approved decisions through placeholder transforms.",
    )
    execute_parser.add_argument("--output", type=Path, default=Path("output"))
    execute_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview execution without writing any files.",
    )
    execute_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of approved images to execute.",
    )
    execute_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-execute items even if already completed in a prior run.",
    )
    execute_parser.add_argument("--profile", default="balanced")
    execute_parser.add_argument("--profile-config", type=Path)
    execute_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from a prior execution_report.json (default behavior).",
    )
    execute_parser.add_argument(
        "--transform",
        choices=TRANSFORMS,
        default="placeholder",
        help="Placeholder transform to dispatch to.",
    )
    execute_parser.add_argument(
        "--cleanup-profile",
        default="watercolor_light",
        help="Cleanup profile name or path (only used with --transform traditional_cleanup).",
    )
    traditional_parser = commands.add_parser(
        "traditional-cleanup",
        help="Preview or run the TraditionalCleanupTransform placeholder via a profile.",
    )
    traditional_parser.add_argument("--output", type=Path, default=Path("output"))
    traditional_parser.add_argument(
        "--input",
        type=Path,
        help="Source image folder for a direct, explicitly approved cleanup run.",
    )
    traditional_parser.add_argument("--profile", default="watercolor_light")
    traditional_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview execution without writing any files.",
    )
    traditional_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of approved images to process.",
    )
    traditional_parser.add_argument(
        "--preview",
        action="store_true",
        help="Show profile, operations, and resource/disk estimates without modifying images.",
    )
    traditional_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-execute items even if already completed in a prior run.",
    )
    args = parser.parse_args(argv)
    try:
        output_path = args.output.expanduser().resolve()
        if args.cleanup_command == "plan":
            manifest_path = (
                args.manifest.expanduser().resolve()
                if args.manifest
                else _latest_manifest_path(output_path)
            )
            manifest = _read_csv(manifest_path)
            health = _read_json_if_exists(output_path / "dataset_health.json")
            recommendations = _read_csv_if_exists(
                output_path / "recommendations.csv"
            )
            registry = PluginRegistry()
            registry.discover("dataset_forge.plugins.builtin")
            user_config = (
                load_structured_file(args.config)
                if args.config
                else {}
            )
            resource_manager = ResourceManager.from_profile(
                args.profile,
                profile_config=args.profile_config,
            )
            plan = CleanupOrchestrator(
                load_cleanup_rules(args.rules)
            ).create_plan(
                manifest,
                health_report=health,
                recommendations=recommendations,
                plugin_metadata=registry.list_plugins(enabled_only=True),
                resource_profile=resource_manager,
                user_config=user_config,
            )
            write_cleanup_plan(output_path, plan)
            if (output_path / OVERRIDES_JSON).is_file():
                PlanControlManager(output_path).write_approved_plan()
            _print_cleanup_summary(plan.to_dict())
            print(f"\nCleanup plan: {output_path / 'cleanup_plan.json'}")
            return 0
        manager = PlanControlManager(output_path)
        if args.cleanup_command == "override":
            changed = manager.override(
                args.image,
                args.action,
                filters=_control_filters(args),
                reason=args.reason,
            )
            _print_control_result(changed)
            return 0
        if args.cleanup_command == "lock":
            changed = manager.lock(
                args.image,
                args.action,
                filters=_control_filters(args),
                reason=args.reason,
            )
            _print_control_result(changed)
            return 0
        if args.cleanup_command == "unlock":
            _print_control_result(manager.unlock(args.image, reason=args.reason))
            return 0
        if args.cleanup_command == "approve":
            filters = _control_filters(args)
            if args.severity:
                filters.append(SelectionFilter("severity", args.severity))
            changed = manager.approve(
                args.image,
                filters=filters,
                reason=args.reason,
            )
            _print_control_result(changed)
            return 0
        if args.cleanup_command == "reject":
            changed = manager.reject(
                args.image,
                filters=_control_filters(args),
                reason=args.reason,
            )
            _print_control_result(changed)
            return 0
        if args.cleanup_command == "approve-all":
            _print_control_result(manager.approve_all(reason=args.reason))
            return 0
        if args.cleanup_command == "reset-overrides":
            manager.reset(reason=args.reason)
            print("User controls reset.")
            return 0
        if args.cleanup_command == "show-overrides":
            print(json.dumps(manager.load_controls(), indent=2))
            return 0
        if args.cleanup_command == "review-plan":
            reviewed = review_plan(manager)
            print(f"\nReviewed decisions: {reviewed}")
            return 0
        if args.cleanup_command == "execute-plan":
            summary = execute_plan(
                output_path,
                dry_run=args.dry_run,
                limit=args.limit,
                force=args.force,
                profile=args.profile,
                profile_config=args.profile_config,
                resume=True,
                transform=args.transform,
                cleanup_profile=args.cleanup_profile,
            )
            _print_execution_summary(summary)
            if summary.dry_run:
                print("\nDry run complete. No files were written.")
            return 0 if summary.failed == 0 else 1
        if args.cleanup_command == "traditional-cleanup":
            if args.input is not None:
                _prepare_direct_cleanup_input(
                    args.input,
                    output_path,
                    limit=args.limit,
                )
            if args.preview:
                _print_traditional_cleanup_preview(output_path, args.profile)
                return 0
            summary = execute_plan(
                output_path,
                dry_run=args.dry_run,
                limit=None if args.input is not None else args.limit,
                force=args.force,
                resume=True,
                transform="traditional_cleanup",
                cleanup_profile=args.profile,
            )
            _print_execution_summary(summary)
            print(f"Selected profile: {summary.cleanup_profile}")
            print(f"Requested operations: {len(summary.requested_operations)}")
            if summary.dry_run:
                print("\nDry run complete. No files were written.")
            return 0 if summary.failed == 0 else 1
        plan_data = load_cleanup_plan(output_path)
        if args.cleanup_command == "summarize-plan":
            _print_cleanup_summary(plan_data)
            return 0
        decision = next(
            (
                item
                for item in plan_data.get("decisions", [])
                if item.get("image_id") == args.image
                or item.get("filename") == args.image
            ),
            None,
        )
        if decision is None:
            raise ValueError(f"Image not found in cleanup plan: {args.image}")
        _print_cleanup_explanation(decision)
        return 0
    except (
        ApprovalRequiredError,
        KeyError,
        OSError,
        PlanControlError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}")
        return 2


def _add_control_arguments(
    parser: argparse.ArgumentParser,
    *,
    where: bool = False,
) -> None:
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--reason", default="")
    if where:
        parser.add_argument("--where", action="append", default=[], metavar="KEY=VALUE")


def _control_filters(args: argparse.Namespace) -> list[SelectionFilter]:
    return [parse_filter(value) for value in getattr(args, "where", [])]


def _print_control_result(decisions: list[dict[str, object]]) -> None:
    for decision in decisions:
        print(
            f"{decision['filename']}: {decision['action']} "
            f"({decision['status']})"
        )
    print(f"Updated decisions: {len(decisions)}")


def _latest_manifest_path(output_path: Path) -> Path:
    pointer = output_path / "manifest_latest.json"
    if pointer.is_file():
        data = _read_json_if_exists(pointer)
        path = output_path / str(data.get("path", ""))
        if path.is_file():
            return path
    legacy = output_path / "manifest.csv"
    if legacy.is_file():
        return legacy
    for name in ("manifest_v3.csv", "manifest_v2.csv", "manifest_v1.csv"):
        candidate = output_path / name
        if candidate.is_file():
            return candidate
    raise ValueError(f"No manifest found under: {output_path}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ValueError(f"Could not read CSV {path}: {exc}") from exc


def _read_csv_if_exists(path: Path) -> list[dict[str, str]]:
    return _read_csv(path) if path.is_file() else []


def _read_json_if_exists(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _print_cleanup_summary(plan: dict[str, object]) -> None:
    counts = dict(plan.get("action_counts", {}))
    labels = (
        ("Keep", CleanupAction.KEEP.value),
        ("Light Cleanup", CleanupAction.CLEAN_LIGHT.value),
        ("Medium Cleanup", CleanupAction.CLEAN_MEDIUM.value),
        ("Strong Cleanup", CleanupAction.CLEAN_STRONG.value),
        (
            "Light Texture Normalization",
            CleanupAction.TEXTURE_NORMALIZE_LIGHT.value,
        ),
        (
            "Medium Texture Normalization",
            CleanupAction.TEXTURE_NORMALIZE_MEDIUM.value,
        ),
        ("Manual Review", CleanupAction.MANUAL_REVIEW.value),
        ("Duplicate Review", CleanupAction.DUPLICATE_REVIEW.value),
        ("Exclude", CleanupAction.EXCLUDE.value),
        ("Regenerate", CleanupAction.REGENERATE.value),
        ("Caption Only", CleanupAction.CAPTION_ONLY.value),
    )
    print(f"Dataset Health: {plan.get('dataset_health_score', 0)}")
    print(f"Total Images: {plan.get('total_images', 0)}")
    for label, action in labels:
        print(f"{label}: {counts.get(action, 0)}")
    print(f"\nEstimated Runtime: {plan.get('estimated_runtime', 'unknown')}")
    print(
        "Estimated Disk Usage: "
        f"{_format_cli_bytes(int(plan.get('estimated_disk_usage', 0) or 0))}"
    )
    print(
        "Estimated GPU Required: "
        f"{'yes' if plan.get('estimated_gpu_required') else 'no'}"
    )
    print(
        "Projected Dataset Health After Cleanup: "
        f"{plan.get('projected_dataset_health', 0)}"
    )
    print(
        "Estimated Artifact Leakage Reduction: "
        f"{plan.get('estimated_artifact_leakage_reduction', 0)}%"
    )


def _print_cleanup_explanation(decision: dict[str, object]) -> None:
    print(f"Image: {decision.get('filename', '')}")
    print(f"Image ID: {decision.get('image_id', '')}")
    print(f"Decision: {decision.get('action', '')}")
    print(f"Confidence: {decision.get('confidence', 0)}")
    print(f"Reason: {decision.get('explanation', '')}")
    print(f"Expected Benefit: {decision.get('expected_benefit', '')}")
    print(f"Recommended Plugin: {decision.get('recommended_plugin', '') or 'none'}")
    print(f"Recommended Preset: {decision.get('recommended_preset', '') or 'none'}")
    print(
        "Recommended Strength: "
        f"{decision.get('recommended_strength', '') or 'none'}"
    )
    warnings = decision.get("warnings", [])
    if warnings:
        print(f"Warnings: {'; '.join(str(item) for item in warnings)}")


def _print_traditional_cleanup_preview(output_path: Path, profile_name: str) -> None:
    profile = load_cleanup_profile(profile_name)
    print(f"Selected profile: {profile.name}")
    if profile.description:
        print(profile.description)

    print("\nOperations that would run:")
    for operation in profile.operations:
        params = ", ".join(
            f"{key}={value}" for key, value in operation.parameters.items()
        )
        suffix = f" ({params})" if params else ""
        print(f"- {operation.name}{suffix}")

    summary = execute_plan(
        output_path,
        dry_run=True,
        transform="traditional_cleanup",
        cleanup_profile=profile_name,
    )

    resource_manager = ResourceManager.from_profile("balanced")
    profile_info = resource_manager.profile.to_dict()
    print("\nEstimated resource usage:")
    print(f"- resource profile: {profile_info.get('name', 'balanced')}")
    print(f"- workers: {resource_manager.worker_count}")
    print(
        "- RAM limit: "
        f"{_format_cli_bytes(int(profile_info.get('ram_limit_mb', 0)) * 1024 * 1024)}"
    )

    disk_usage = sum(
        Path(str(record["source_path"])).stat().st_size
        for record in summary.records
        if record["status"] == "dry-run" and record["source_path"]
    )
    print("\nEstimated disk usage:")
    print(f"- {_format_cli_bytes(disk_usage)} across {summary.executed} image(s)")


def _prepare_direct_cleanup_input(
    input_path: Path,
    output_path: Path,
    *,
    limit: int | None,
) -> None:
    discovery = discover_images(
        input_path.expanduser().resolve(),
        recursive=False,
        limit=limit,
        excluded_root=output_path,
    )
    if not discovery.images:
        raise ValueError(f"No supported images found under: {input_path}")
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path / "manifest_v1.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "original_path"])
        writer.writeheader()
        for source in discovery.images:
            writer.writerow(
                {"filename": source.name, "original_path": str(source)}
            )
    (output_path / "manifest_latest.json").write_text(
        json.dumps({"version": 1, "path": manifest_path.name}, indent=2) + "\n",
        encoding="utf-8",
    )
    decisions = [
        {
            "image_id": _direct_image_id(source),
            "filename": source.name,
            "action": CleanupAction.CLEAN_LIGHT.value,
            "confidence": 100,
            "explanation": "Direct traditional-cleanup command requested by the user.",
            "expected_benefit": "Conservative deterministic microcleanup.",
            "before_quality_score": 0,
            "estimated_after_quality_score": 0,
            "estimated_quality_delta": 0,
            "recommended_plugin": "cleanup.traditional_cleanup",
            "recommended_preset": "",
            "recommended_strength": "light",
            "estimated_runtime": "seconds",
            "estimated_disk_write": source.stat().st_size,
            "estimated_gpu_required": False,
            "warnings": [],
        }
        for source in discovery.images
    ]
    (output_path / "cleanup_plan.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_images": len(decisions),
                "action_counts": {"CLEAN_LIGHT": len(decisions)},
                "decisions": decisions,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    PlanControlManager(output_path).approve_all(
        reason="Explicit traditional-cleanup --input command"
    )


def _direct_image_id(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _print_execution_summary(summary: ExecutionSummary) -> None:
    print(f"Approved items: {summary.approved_items}")
    print(f"Executed: {summary.executed}")
    print(f"Skipped: {summary.skipped}")
    print(f"Failed: {summary.failed}")
    print(f"Output folder: {summary.processed_dir}")
    print(f"Total disk written: {_format_cli_bytes(summary.total_disk_written)}")


def _format_cli_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024**2:
        return f"{value / 1024:.1f} KB"
    if value < 1024**3:
        return f"{value / 1024**2:.1f} MB"
    return f"{value / 1024**3:.1f} GB"


def _plugins_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset-forge plugins",
        description="Inspect and manage Dataset Forge plugins.",
    )
    commands = parser.add_subparsers(dest="plugin_command", required=True)
    list_parser = commands.add_parser("list", help="List discovered plugins.")
    list_parser.add_argument("--config", type=Path)
    info_parser = commands.add_parser("info", help="Show plugin metadata.")
    info_parser.add_argument("plugin_id")
    info_parser.add_argument("--config", type=Path)
    enable_parser = commands.add_parser("enable", help="Enable a plugin.")
    enable_parser.add_argument("plugin_id")
    disable_parser = commands.add_parser("disable", help="Disable a plugin.")
    disable_parser.add_argument("plugin_id")
    args = parser.parse_args(argv[1:])
    try:
        registry = PluginRegistry()
        registry.discover("dataset_forge.plugins.builtin")
        config = getattr(args, "config", None)
        if config:
            registry.configure(config)
        if args.plugin_command == "list":
            plugins = registry.list_plugins()
            print("Discovered plugins:")
            for plugin in plugins:
                status = "enabled" if plugin["enabled"] else "disabled"
                print(
                    f"- {plugin['id']} [{plugin['category']}, {status}] "
                    f"{plugin['name']} {plugin['version']}"
                )
            return 0
        if args.plugin_command == "info":
            print(json.dumps(registry.info(args.plugin_id), indent=2))
            return 0
        if args.plugin_command == "enable":
            registry.enable(args.plugin_id)
            print(f"Enabled plugin: {args.plugin_id}")
            return 0
        registry.disable(args.plugin_id)
        print(f"Disabled plugin: {args.plugin_id}")
        return 0
    except (KeyError, OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2


def _add_resource_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        default="balanced",
        help="Execution profile: eco, balanced, max, overnight, or custom.",
    )
    parser.add_argument(
        "--profile-config",
        type=Path,
        help="JSON or YAML file containing execution profiles.",
    )
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--cpu-limit", type=int)
    parser.add_argument("--ram-limit", type=int)
    parser.add_argument(
        "--io-throttle",
        choices=("low", "medium", "high", "unlimited"),
    )
    parser.add_argument(
        "--cache-policy",
        choices=("none", "minimal", "standard", "aggressive"),
    )
    parser.add_argument("--adaptive", action="store_true", default=None)


def _resource_manager_from_args(args: argparse.Namespace) -> ResourceManager:
    return ResourceManager.from_profile(
        args.profile,
        profile_config=args.profile_config,
        overrides={
            "max_workers": args.max_workers,
            "cpu_target_percent": args.cpu_limit,
            "ram_limit_mb": args.ram_limit,
            "io_throttle": args.io_throttle,
            "cache_policy": args.cache_policy,
            "adaptive_mode": args.adaptive,
        },
    )


def _print_summary(summary: PipelineSummary) -> None:
    print("\nSummary")
    print(f"Images found:     {summary.images_found}")
    print(f"Images processed: {summary.images_processed}")
    print(f"Skipped files:    {summary.skipped_files}")
    print(f"Errors:           {summary.errors}")
    if summary.health:
        print(f"\nDataset Health: {summary.health.dataset_health_score:.0f}/100")
        print(
            f"Images requiring cleanup: "
            f"{summary.health.images_requiring_cleanup}"
        )
        print(f"Likely duplicates: {summary.health.likely_duplicates}")
        print(f"Low resolution images: {summary.health.low_resolution_images}")
        print(f"Critical issues: {summary.health.critical_issues}")
        print(f"Warnings: {summary.health.warnings}")


def _print_presets() -> None:
    presets = list_presets()
    if not presets:
        print("No presets found.")
        return
    print("Available presets:")
    for preset in presets:
        print(f"- {preset.source.stem}: {preset.name}")
        print(f"  {preset.description}")


if __name__ == "__main__":
    raise SystemExit(main())
