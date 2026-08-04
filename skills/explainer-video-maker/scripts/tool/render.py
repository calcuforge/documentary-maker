#!/usr/bin/env python3
"""
Render video using remotion-video-template.

Calls the render-yaml.mjs script in the remotion-video-template project,
passing the remotion_sections.yaml configuration.

Usage:
    python render.py --remotion-sections /abs/path/remotion_sections.yaml \
                     --project-config /abs/path/project_config.yaml \
                     --output /abs/path/result.mp4

Options:
    --remotion-sections  Path to remotion_sections.yaml (required)
    --project-config     Path to project_config.yaml (required)
    --output             Output video file path (required)
    --studio             Launch Remotion Studio instead of rendering
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import lzma
import tarfile
import time
import uuid
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml

try:
    import requests
except ImportError:
    requests = None

DISTRIBUTED_WORK_DIR = ".distributed_render"  # workspace 下的分布式渲染工作目录
DISTRIBUTED_POLL_INTERVAL = 10  # 轮询间隔(秒)
DISTRIBUTED_TIMEOUT = 7200  # 轮询总超时(秒)，服务端 max_exec_time_sec 超时后会返回 timeout 状态


def resolve_template_path(project_config: dict) -> Path:
    """Resolve the remotion-video-template path from project config.

    The default location is the workspace's dep/ directory
    (dep/remotion-video-template). A `~`-prefixed or absolute path is used as-is
    (after ~ expansion); a genuinely relative path resolves against the workspace
    (the directory that contains projects/).
    """
    dep = project_config.get("dependence_paths", {})
    template_rel = dep.get("remotion_template", "dep/remotion-video-template")

    expanded = os.path.expanduser(template_rel)
    if os.path.isabs(expanded):
        return Path(expanded)

    project_root = project_config.get("project", {}).get("project_root_path", "")
    base = Path(project_root).parent.parent if project_root else Path.cwd()
    return (base / expanded).resolve()


def render_distributed(args, project_config, template_path) -> None:
    """Distributed render via proxy_agent (render.mode=distributed).

    Packs the video assets (public-dir) and the remotion template source into a
    tar.xz, uploads it to the proxy agent, polls the render task and moves the
    rendered result.mp4 (copied back into the container by the proxy agent)
    into the project output path. Billing is handled server-side by duration.
    """
    if requests is None:
        print(json.dumps({
            "status": "error",
            "msg": "requests library not available — install requests to use distributed rendering",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    proxy_endpoint = os.path.expandvars(os.environ.get("BACKEND_PROXY_ENDPOINT", "${BACKEND_PROXY_ENDPOINT}"))
    if proxy_endpoint.startswith("${"):
        print(json.dumps({
            "status": "error",
            "msg": "BACKEND_PROXY_ENDPOINT is not set — distributed rendering unavailable",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    proxy_endpoint = proxy_endpoint.rstrip("/")

    sections_path = str(Path(args.remotion_sections).resolve())
    output_path = str(Path(args.output).resolve())
    public_dir = Path(args.remotion_sections).resolve().parent

    project_root = project_config.get("project", {}).get("project_root_path", "")
    workspace = Path(project_root).parent.parent if project_root else public_dir.parent

    render_cfg = project_config.get("render") or {}
    poll_interval = render_cfg.get("poll_interval_sec") or DISTRIBUTED_POLL_INTERVAL
    sections_file = render_cfg.get("sections_file") or "remotion_sections.yaml"

    task_id = uuid.uuid4().hex[:12]
    workdir = workspace / DISTRIBUTED_WORK_DIR / task_id
    workdir.mkdir(parents=True, exist_ok=True)
    payload_path = workdir / "render_payload.tar.xz"

    # 分布式渲染进度日志写到项目目录的 render.log(与本地模式一致)
    log_path = Path(output_path).parent / "render.log"
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)
        try:
            log_file.write(msg + "\n")
            log_file.flush()
        except Exception:
            pass

    try:
        # 1. 打包素材(public-dir)+ 模板源码(不含 node_modules/.git/tmp)
        # 最快模式压缩(LZMA preset 0:体积最大、压缩速度最快;素材多为已压缩的媒体文件)
        log(f"Packing assets + template (fast compression)...")
        xz_f = lzma.LZMAFile(str(payload_path), mode="w", preset=0)
        try:
            tar = tarfile.open(fileobj=xz_f, mode="w")
        except Exception:
            xz_f.close()
            raise
        with tar:
            for p in sorted(public_dir.rglob("*")):
                rel = p.relative_to(public_dir)
                if any(part == "tmp" for part in rel.parts):
                    continue
                if p.is_file() and rel.name == "result.mp4":
                    continue
                if p.is_file() and rel.name.startswith("origin_"):
                    # Pre-upscale / pre-compression raw inputs (scenes/origin_*)
                    # — Remotion renders from asset_path only, so skip them.
                    continue
                arc = "public/" + rel.as_posix()
                tar.add(str(p), arcname=arc, recursive=False)
            skip_dirs = {"node_modules", ".git", "tmp"}
            for p in sorted(template_path.rglob("*")):
                rel = p.relative_to(template_path)
                if any(part in skip_dirs for part in rel.parts):
                    continue
                arc = "template/remotion-video-template/" + rel.as_posix()
                tar.add(str(p), arcname=arc, recursive=False)
        # tarfile 关闭时不关闭外部 fileobj,需显式写入 xz 尾部
        if not xz_f.closed:
            xz_f.close()
        size_mb = payload_path.stat().st_size / (1024 * 1024)
        log(f"Payload: {payload_path} ({size_mb:.1f} MB)")

        # 2. 上传发起分布式渲染
        submit_url = f"{proxy_endpoint}/render/submit"
        log(f"Submitting render task to {submit_url} ...")
        last_err = None
        for attempt in range(2):
            try:
                with open(payload_path, "rb") as f:
                    r = requests.post(
                        submit_url,
                        files={"file": (payload_path.name, f, "application/x-xz")},
                        data={
                            "container_payload_path": str(payload_path),
                            "sections_file": sections_file,
                        },
                        timeout=600,
                    )
                if r.status_code != 200:
                    last_err = f"submit returned status {r.status_code}: {r.text[:500]}"
                    continue
                resp = r.json()
                task_id = resp.get("task_id", task_id)
                break
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(2)
        else:
            print(json.dumps({
                "status": "error",
                "msg": f"Failed to submit distributed render task: {last_err}",
                "data": {},
            }, ensure_ascii=False, indent=2))
            sys.exit(1)
        log(f"Render task submitted: {task_id}")

        # 3. 轮询任务状态
        status_url = f"{proxy_endpoint}/render/status"
        deadline = time.time() + DISTRIBUTED_TIMEOUT
        final_status = None
        final_error = ""
        while time.time() < deadline:
            time.sleep(int(poll_interval))
            try:
                r = requests.get(status_url, params={"task_id": task_id}, timeout=60)
                if r.status_code != 200:
                    print(json.dumps({
                        "status": "error",
                        "msg": f"status query failed: {r.status_code} {r.text[:500]}",
                        "data": {"task_id": task_id},
                    }, ensure_ascii=False, indent=2))
                    sys.exit(1)
                j = r.json()
                final_status = j.get("status")
                final_error = j.get("error") or ""
                if final_status in ("success", "failed", "timeout", "cancelled"):
                    break
                log(f"  render status: {final_status} ...")
            except requests.RequestException as e:
                print(json.dumps({
                    "status": "error",
                    "msg": f"status query failed: {e}",
                    "data": {"task_id": task_id},
                }, ensure_ascii=False, indent=2))
                sys.exit(1)

        if final_status != "success":
            print(json.dumps({
                "status": "error",
                "msg": f"Distributed render {final_status or 'timeout'}: {final_error or 'no result'}"[:2000],
                "data": {"task_id": task_id},
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        # 4. 结果已由 proxy_agent 拷回容器工作目录,移动到项目输出路径
        result_src = workdir / "result.mp4"
        if not result_src.exists():
            print(json.dumps({
                "status": "error",
                "msg": f"result.mp4 not found in container work dir: {result_src}",
                "data": {"task_id": task_id},
            }, ensure_ascii=False, indent=2))
            sys.exit(1)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(result_src), output_path)
        out_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        print(json.dumps({
            "status": "ok",
            "msg": f"Video rendered successfully (distributed): {output_path}",
            "data": {
                "output": output_path,
                "size_mb": round(out_size_mb, 1),
                "task_id": task_id,
            },
        }, ensure_ascii=False, indent=2))
    finally:
        # 5. 清理容器内工作目录(压缩包+下载结果)
        shutil.rmtree(workdir, ignore_errors=True)
        try:
            log_file.close()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render video via remotion-video-template")
    parser.add_argument("--remotion-sections", required=True, help="Path to remotion_sections.yaml (absolute)")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--output", required=True, help="Output video file path (absolute)")
    parser.add_argument("--studio", action="store_true", help="Launch Studio instead of rendering")
    parser.add_argument("--timeout", type=int, default=3600, help="Render timeout (seconds, default 1h)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.remotion_sections, args.project_config, args.output)

    project_config = load_yaml(args.project_config)
    template_path = resolve_template_path(project_config)

    if not template_path.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"remotion-video-template not found at: {template_path}",
            "data": {"hint": "Set dependence_paths.remotion_template in project_config.yaml"},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    render_script = template_path / "render-yaml.mjs"
    if not render_script.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"render-yaml.mjs not found in {template_path}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    render_cfg = project_config.get("render") or {}
    mode = str(render_cfg.get("mode", "local")).strip().lower()

    if mode == "distributed" and not args.studio:
        render_distributed(args, project_config, template_path)
        return

    sections_path = str(Path(args.remotion_sections).resolve())
    output_path = str(Path(args.output).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Use the video directory as public-dir (contains audio + assets)
    public_dir = str(Path(args.remotion_sections).parent)

    if args.studio:
        # Launch Studio
        cmd = ["node", str(render_script), sections_path, "--studio"]
        print(f"Launching Remotion Studio...", file=sys.stderr)
        print(f"  Config: {sections_path}", file=sys.stderr)
        print(f"  Template: {template_path}", file=sys.stderr)
        try:
            subprocess.run(cmd, cwd=str(template_path))
        except KeyboardInterrupt:
            pass
        return

    # Render — render-yaml.mjs splits the video into frame-range segments and
    # concatenates them with ffmpeg, with adaptive parallelism (per-render
    # concurrency capped at 8, extra segment workers when CPU allows).
    # segment_frames / segment_workers are optional tuning knobs (render-yaml.mjs
    # applies its own defaults when they are not set).
    segment_frames = render_cfg.get("segment_frames")
    segment_workers = render_cfg.get("segment_workers")

    cmd = [
        "node", str(render_script),
        sections_path,
        "--public-dir", public_dir,
        "--output", output_path,
    ]
    if segment_frames:
        cmd.extend(["--segment-frames", str(segment_frames)])
    if segment_workers:
        cmd.extend(["--segment-workers", str(segment_workers)])

    print(f"Rendering video...", file=sys.stderr)
    print(f"  Config: {sections_path}", file=sys.stderr)
    print(f"  Public dir: {public_dir}", file=sys.stderr)
    print(f"  Output: {output_path}", file=sys.stderr)
    print(f"  Template: {template_path}", file=sys.stderr)
    print(f"  Segment frames: {segment_frames or '(default)'}", file=sys.stderr)
    print(f"  Segment workers: {segment_workers or '(default)'}", file=sys.stderr)

    # Write render output to a log file instead of capturing via pipes.
    # capture_output=True buffers ALL stdout/stderr in memory — for a long
    # segmented render this can be tens of MB and causes pipe-buffer
    # deadlocks or OOM on Windows. A log file avoids both problems.
    log_path = Path(output_path).parent / "render.log"
    print(f"  Log: {log_path}", file=sys.stderr)

    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            proc = subprocess.run(
                cmd,
                cwd=str(template_path),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
            )
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "status": "error",
            "msg": f"Render timed out after {args.timeout}s",
            "data": {"log": str(log_path)},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "msg": "node not found on PATH — install Node.js >= 18",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except OSError as e:
        print(json.dumps({
            "status": "error",
            "msg": f"Failed to start render process: {e}",
            "data": {"log": str(log_path)},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    if proc.returncode != 0:
        # Read the tail of the log for error diagnostics
        log_tail = ""
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = log_text[-3000:] if log_text else ""
        except OSError:
            pass
        print(json.dumps({
            "status": "error",
            "msg": "Render failed",
            "data": {"log": str(log_path), "log_tail": log_tail},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Verify output exists
    if not Path(output_path).exists():
        log_tail = ""
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = log_text[-1000:] if log_text else ""
        except OSError:
            pass
        print(json.dumps({
            "status": "error",
            "msg": f"Output file not created: {output_path}",
            "data": {"log": str(log_path), "log_tail": log_tail},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Get file size
    size_mb = Path(output_path).stat().st_size / (1024 * 1024)

    print(json.dumps({
        "status": "ok",
        "msg": f"Video rendered successfully: {output_path}",
        "data": {
            "output": output_path,
            "size_mb": round(size_mb, 1),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
