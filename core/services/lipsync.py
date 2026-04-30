import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from core.services.language_avatar import (
    configured_avatar_entries,
    preload_target_avatar_videos,
    resolve_avatar_video_for_group,
    tts_speaker_for_group,
)
from core.services.speech import synthesize_tts


MUSE_WORKER_LOCK = threading.Lock()
MUSE_WORKERS: dict[str, "MuseWorkerState"] = {}
MUSE_WARMUP_STARTED = False
MUSE_PRELOAD_THREAD: threading.Thread | None = None
MUSE_PRELOAD_ERROR = ""
SADTALKER_WARMUP_STARTED = False
SWITCH_CACHE_LOCK = threading.Lock()


@dataclass
class MuseWorkerState:
    avatar_signature: str
    avatar_id: str
    avatar_video: Path
    job_dir: Path
    ready_flag: Path
    proc: subprocess.Popen
    last_used_at: float


if settings.NON_LIPSYNC_FORCE_CPU:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


def run_command(cmd, cwd: Path | None = None, env: dict | None = None):
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        details = "\n".join(part for part in [stdout, stderr] if part)
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(map(str, cmd))}\n{details}")


def python_executable_works(candidate: Path | None) -> bool:
    if candidate is None:
        return False
    candidate = candidate.resolve()
    if not candidate.exists():
        return False
    try:
        proc = subprocess.run(
            [str(candidate), "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except Exception:
        return False


def resolve_python_executable(label: str, configured_path: str, fallback_candidates: list[Path]) -> str:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in [Path(configured_path).resolve() if configured_path else None, *fallback_candidates, Path(sys.executable).resolve()]:
        if raw is None:
            continue
        key = str(raw)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(raw)

    broken: list[str] = []
    for candidate in candidates:
        if python_executable_works(candidate):
            return str(candidate)
        if candidate.exists():
            broken.append(str(candidate))

    if broken:
        raise RuntimeError(
            f"No working Python interpreter found for {label}. "
            f"These executables exist but could not be launched: {', '.join(broken)}"
        )
    raise RuntimeError(f"No Python interpreter found for {label}.")


def lipsync_env(gpu_id: int) -> dict:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    return env


def bootstrap_sadtalker(repo_dir: Path):
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (repo_dir / ".git").exists():
        if repo_dir.exists():
            raise RuntimeError(f"SadTalker directory exists but is not a git repo: {repo_dir}")
        run_command(["git", "clone", "--depth", "1", settings.SADTALKER_GITHUB_URL, str(repo_dir)])

    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        run_command([sys.executable, "-m", "pip", "install", "-r", str(requirements)])

    download_scripts = [
        [sys.executable, str(repo_dir / "scripts" / "download_models.py")],
        ["cmd", "/c", str(repo_dir / "scripts" / "download_models.bat")],
    ]
    for cmd in download_scripts:
        if Path(cmd[-1]).exists():
            try:
                run_command(cmd, cwd=repo_dir)
                break
            except Exception:
                continue


def resolve_sadtalker_script() -> Path:
    if settings.SADTALKER_PATH:
        script = Path(settings.SADTALKER_PATH).resolve()
        if not script.exists():
            raise RuntimeError(f"SADTALKER_PATH does not exist: {script}")
        return script
    repo_dir = Path(settings.SADTALKER_DIR).resolve()
    script = (repo_dir / "inference.py").resolve()
    if script.exists():
        return script
    if not settings.SADTALKER_AUTO_SETUP:
        raise RuntimeError(
            "SadTalker is not available. Enable SADTALKER_AUTO_SETUP=1 or set SADTALKER_PATH to inference.py."
        )
    bootstrap_sadtalker(repo_dir)
    if not script.exists():
        raise RuntimeError("SadTalker auto-setup did not produce inference.py. Check SADTALKER_DIR.")
    return script


def resolve_sadtalker_python() -> str:
    fallback_candidates = [Path(settings.BASE_DIR) / ".venv" / "Scripts" / "python.exe"]
    return resolve_python_executable("SadTalker", settings.SADTALKER_PYTHON, fallback_candidates)


def run_sadtalker_lipsync(avatar_image: Path, speech_audio: Path, output_video: Path) -> str:
    script = resolve_sadtalker_script()
    python_exe = resolve_sadtalker_python()
    repo_dir = script.parent.resolve()
    result_dir = output_video.parent / f"{output_video.stem}_sadtalker"
    result_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        python_exe,
        str(script),
        "--source_image",
        str(avatar_image),
        "--driven_audio",
        str(speech_audio),
        "--result_dir",
        str(result_dir),
    ]
    extra_args = settings.SADTALKER_EXTRA_ARGS.strip()
    if extra_args:
        cmd.extend(extra_args.split())
    run_command(cmd, cwd=repo_dir, env=lipsync_env(settings.LIPSYNC_GPU_ID))

    mp4_candidates = sorted(result_dir.rglob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not mp4_candidates:
        raise RuntimeError("SadTalker completed but no output mp4 was found.")
    mp4_candidates[0].replace(output_video)
    return "sadtalker"


def resolve_musetalk_repo() -> Path:
    repo_dir = Path(settings.MUSE_TALK_DIR).resolve()
    if not repo_dir.exists():
        raise RuntimeError(f"MuseTalk directory does not exist: {repo_dir}")
    if not (repo_dir / "scripts" / "inference.py").exists():
        raise RuntimeError(f"MuseTalk inference script not found in: {repo_dir}")
    return repo_dir


def resolve_musetalk_python() -> str:
    fallback_candidates = [Path(settings.BASE_DIR) / ".venv" / "Scripts" / "python.exe"]
    return resolve_python_executable("MuseTalk", settings.MUSE_TALK_PYTHON, fallback_candidates)


def musetalk_runtime_profile() -> tuple[int, int]:
    if settings.MUSE_TALK_USE_FAST_PROFILE:
        fps = min(max(10, settings.MUSE_TALK_FAST_FPS), 25)
        batch_size = min(max(1, settings.MUSE_TALK_FAST_BATCH_SIZE), 16)
    else:
        fps = min(max(12, settings.MUSE_TALK_FPS), 25)
        batch_size = min(max(1, settings.MUSE_TALK_BATCH_SIZE), 16)
    return fps, batch_size


def run_musetalk_lipsync(avatar_video: Path, speech_audio: Path, output_video: Path) -> str:
    if settings.MUSE_TALK_PERSISTENT_WORKER:
        try:
            return run_musetalk_lipsync_persistent(avatar_video, speech_audio, output_video)
        except Exception:
            return run_musetalk_lipsync_oneshot(avatar_video, speech_audio, output_video)
    return run_musetalk_lipsync_oneshot(avatar_video, speech_audio, output_video)


def run_musetalk_lipsync_oneshot(avatar_video: Path, speech_audio: Path, output_video: Path) -> str:
    repo_dir = resolve_musetalk_repo()
    python_exe = resolve_musetalk_python()
    version = (settings.MUSE_TALK_VERSION or "v15").strip().lower()
    if version not in {"v1", "v15"}:
        version = "v15"

    result_dir = output_video.parent / f"{output_video.stem}_musetalk"
    result_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = result_dir / "inference.yaml"
    cfg_path.write_text(
        (
            "task_0:\n"
            f"  video_path: \"{avatar_video.as_posix()}\"\n"
            f"  audio_path: \"{speech_audio.as_posix()}\"\n"
            "  result_name: \"output.mp4\"\n"
        ),
        encoding="utf-8",
    )

    if version == "v1":
        unet_model_path = repo_dir / "models" / "musetalk" / "pytorch_model.bin"
        unet_config_path = repo_dir / "models" / "musetalk" / "musetalk.json"
    else:
        unet_model_path = repo_dir / "models" / "musetalkV15" / "unet.pth"
        unet_config_path = repo_dir / "models" / "musetalkV15" / "musetalk.json"

    fps, batch_size = musetalk_runtime_profile()
    cmd = [
        python_exe,
        "-X",
        "utf8",
        "-m",
        "scripts.inference",
        "--inference_config",
        str(cfg_path),
        "--result_dir",
        str(result_dir),
        "--unet_model_path",
        str(unet_model_path),
        "--unet_config",
        str(unet_config_path),
        "--whisper_dir",
        str(repo_dir / "models" / "whisper"),
        "--version",
        version,
        "--gpu_id",
        str(settings.MUSE_TALK_GPU_ID),
        "--fps",
        str(fps),
        "--batch_size",
        str(batch_size),
        "--extra_margin",
        str(settings.MUSE_TALK_EXTRA_MARGIN),
        "--audio_padding_length_left",
        str(settings.MUSE_TALK_AUDIO_PADDING_LEFT),
        "--audio_padding_length_right",
        str(settings.MUSE_TALK_AUDIO_PADDING_RIGHT),
    ]
    if settings.MUSE_TALK_USE_FLOAT16:
        cmd.append("--use_float16")
    if settings.MUSE_TALK_USE_SAVED_COORD:
        cmd.append("--use_saved_coord")
    if settings.MUSE_TALK_SAVE_COORD:
        cmd.append("--saved_coord")
    if settings.MUSE_TALK_FFMPEG_PATH.strip():
        cmd.extend(["--ffmpeg_path", settings.MUSE_TALK_FFMPEG_PATH.strip()])

    run_command(cmd, cwd=repo_dir, env=lipsync_env(settings.MUSE_TALK_GPU_ID))

    expected = result_dir / version / "output.mp4"
    if expected.exists():
        expected.replace(output_video)
        return "musetalk"

    mp4_candidates = sorted(result_dir.rglob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not mp4_candidates:
        raise RuntimeError("MuseTalk completed but no output mp4 was found.")
    mp4_candidates[0].replace(output_video)
    return "musetalk"


def musetalk_avatar_signature(avatar_video: Path) -> str:
    stat = avatar_video.stat()
    payload = f"{avatar_video.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def musetalk_avatar_id(avatar_signature: str) -> str:
    return f"default_avatar_{avatar_signature}"


def musetalk_job_dir(avatar_signature: str) -> Path:
    job_dir = Path(settings.MEDIA_ROOT) / "musetalk_worker" / avatar_signature
    (job_dir / "in").mkdir(parents=True, exist_ok=True)
    (job_dir / "out").mkdir(parents=True, exist_ok=True)
    (job_dir / "tmp").mkdir(parents=True, exist_ok=True)
    return job_dir


def max_musetalk_vram_avatars() -> int:
    if not settings.MUSE_TALK_MULTI_AVATAR_POOL:
        return 1
    return max(1, settings.MUSE_TALK_MAX_VRAM_AVATARS)


def musetalk_avatar_cache_dir(avatar_video: Path) -> Path:
    repo_dir = resolve_musetalk_repo()
    version = (settings.MUSE_TALK_VERSION or "v15").strip().lower()
    if version not in {"v1", "v15"}:
        version = "v15"
    avatar_signature = musetalk_avatar_signature(avatar_video)
    avatar_id = musetalk_avatar_id(avatar_signature)
    if version == "v15":
        return repo_dir / "results" / version / "avatars" / avatar_id
    return repo_dir / "results" / "avatars" / avatar_id


def musetalk_avatar_cache_ready(avatar_video: Path) -> bool:
    avatar_cache_dir = musetalk_avatar_cache_dir(avatar_video)
    required = [
        avatar_cache_dir / "latents.pt",
        avatar_cache_dir / "coords.pkl",
        avatar_cache_dir / "mask_coords.pkl",
        avatar_cache_dir / "avator_info.json",
    ]
    return all(path.exists() for path in required)


def worker_alive(worker: MuseWorkerState) -> bool:
    return worker.proc.poll() is None


def cleanup_dead_musetalk_workers_locked():
    dead_signatures = [signature for signature, worker in MUSE_WORKERS.items() if not worker_alive(worker)]
    for signature in dead_signatures:
        MUSE_WORKERS.pop(signature, None)


def stop_musetalk_worker_locked(avatar_signature: str):
    worker = MUSE_WORKERS.pop(avatar_signature, None)
    if worker is None or worker.proc.poll() is not None:
        return
    worker.proc.terminate()
    try:
        worker.proc.wait(timeout=10)
    except Exception:
        worker.proc.kill()
        worker.proc.wait(timeout=5)


def evict_lru_musetalk_worker_locked():
    if not MUSE_WORKERS:
        return
    lru_signature = min(MUSE_WORKERS.items(), key=lambda item: item[1].last_used_at)[0]
    stop_musetalk_worker_locked(lru_signature)


def ensure_musetalk_worker(avatar_video: Path) -> MuseWorkerState:
    with MUSE_WORKER_LOCK:
        avatar_video = avatar_video.resolve()
        avatar_signature = musetalk_avatar_signature(avatar_video)
        existing = MUSE_WORKERS.get(avatar_signature)
        if existing and worker_alive(existing):
            existing.last_used_at = time.time()
            return existing

        cleanup_dead_musetalk_workers_locked()
        while len(MUSE_WORKERS) >= max_musetalk_vram_avatars():
            evict_lru_musetalk_worker_locked()

        repo_dir = resolve_musetalk_repo()
        python_exe = resolve_musetalk_python()
        version = (settings.MUSE_TALK_VERSION or "v15").strip().lower()
        if version not in {"v1", "v15"}:
            version = "v15"
        if version == "v1":
            unet_model_path = repo_dir / "models" / "musetalk" / "pytorch_model.bin"
            unet_config_path = repo_dir / "models" / "musetalk" / "musetalk.json"
        else:
            unet_model_path = repo_dir / "models" / "musetalkV15" / "unet.pth"
            unet_config_path = repo_dir / "models" / "musetalkV15" / "musetalk.json"

        job_dir = musetalk_job_dir(avatar_signature)
        ready_flag = job_dir / "ready.flag"
        if ready_flag.exists():
            ready_flag.unlink()

        avatar_id = musetalk_avatar_id(avatar_signature)
        server_preparation = not musetalk_avatar_cache_ready(avatar_video)
        fps, batch_size = musetalk_runtime_profile()
        cmd = [
            python_exe,
            "-X",
            "utf8",
            "-m",
            "scripts.realtime_inference",
            "--server_mode",
            "--non_interactive",
            "--job_dir",
            str(job_dir),
            "--server_avatar_id",
            avatar_id,
            "--server_avatar_path",
            str(avatar_video),
            "--gpu_id",
            str(settings.MUSE_TALK_GPU_ID),
            "--version",
            version,
            "--fps",
            str(fps),
            "--batch_size",
            str(batch_size),
            "--unet_model_path",
            str(unet_model_path),
            "--unet_config",
            str(unet_config_path),
            "--whisper_dir",
            str(repo_dir / "models" / "whisper"),
            "--extra_margin",
            str(settings.MUSE_TALK_EXTRA_MARGIN),
            "--audio_padding_length_left",
            str(settings.MUSE_TALK_AUDIO_PADDING_LEFT),
            "--audio_padding_length_right",
            str(settings.MUSE_TALK_AUDIO_PADDING_RIGHT),
        ]
        if server_preparation:
            cmd.append("--server_preparation")
        if settings.MUSE_TALK_FFMPEG_PATH.strip():
            cmd.extend(["--ffmpeg_path", settings.MUSE_TALK_FFMPEG_PATH.strip()])

        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=lipsync_env(settings.MUSE_TALK_GPU_ID),
        )
        worker = MuseWorkerState(
            avatar_signature=avatar_signature,
            avatar_id=avatar_id,
            avatar_video=avatar_video,
            job_dir=job_dir,
            ready_flag=ready_flag,
            proc=proc,
            last_used_at=time.time(),
        )
        MUSE_WORKERS[avatar_signature] = worker

        start = time.time()
        while time.time() - start < settings.MUSE_TALK_WORKER_TIMEOUT_SEC:
            if worker.proc.poll() is not None:
                MUSE_WORKERS.pop(avatar_signature, None)
                raise RuntimeError(f"MuseTalk worker exited early for avatar: {avatar_video.name}")
            if ready_flag.exists():
                worker.last_used_at = time.time()
                return worker
            time.sleep(0.2)

        stop_musetalk_worker_locked(avatar_signature)
        raise RuntimeError(f"MuseTalk worker did not become ready in time for avatar: {avatar_video.name}")


def run_musetalk_lipsync_persistent(avatar_video: Path, speech_audio: Path, output_video: Path) -> str:
    worker = ensure_musetalk_worker(avatar_video)
    job_dir = worker.job_dir
    job_id = output_video.stem
    in_file = job_dir / "in" / f"{job_id}.json"
    out_file = job_dir / "out" / f"{job_id}.json"
    if out_file.exists():
        out_file.unlink()

    in_file.write_text(
        json.dumps(
            {
                "audio_path": str(speech_audio).replace("\\", "/"),
                "output_path": str(output_video).replace("\\", "/"),
            }
        ),
        encoding="utf-8",
    )

    start = time.time()
    while time.time() - start < settings.MUSE_TALK_WORKER_TIMEOUT_SEC:
        if out_file.exists():
            payload = out_file.read_text(encoding="utf-8")
            out_file.unlink(missing_ok=True)
            result = json.loads(payload)
            if result.get("ok"):
                if output_video.exists():
                    worker.last_used_at = time.time()
                    return "musetalk"
                raise RuntimeError("MuseTalk worker reported success but output video is missing.")
            raise RuntimeError(f"MuseTalk worker failed: {result.get('error') or payload}")
        time.sleep(0.1)
    raise RuntimeError("MuseTalk worker job timeout.")


def run_lipsync(model_name: str, avatar_video: Path, avatar_image: Path, speech_audio: Path, output_video: Path) -> str:
    model = (model_name or "").strip().lower()
    if model in {"none", "off", "skip"}:
        return "none"
    if model == "musetalk":
        return run_musetalk_lipsync(avatar_video, speech_audio, output_video)
    return run_sadtalker_lipsync(avatar_image, speech_audio, output_video)


def preload_musetalk_workers_sync():
    global MUSE_PRELOAD_ERROR
    if not settings.MUSE_TALK_PERSISTENT_WORKER:
        raise RuntimeError("MuseTalk persistent worker mode is disabled.")
    for avatar_video in preload_target_avatar_videos():
        ensure_musetalk_worker(avatar_video)
    MUSE_PRELOAD_ERROR = ""


def start_musetalk_preload_thread() -> bool:
    global MUSE_PRELOAD_THREAD, MUSE_PRELOAD_ERROR
    with MUSE_WORKER_LOCK:
        if MUSE_PRELOAD_THREAD is not None and MUSE_PRELOAD_THREAD.is_alive():
            return False

        def runner():
            global MUSE_PRELOAD_ERROR
            try:
                preload_musetalk_workers_sync()
            except Exception as exc:
                MUSE_PRELOAD_ERROR = str(exc).strip() or exc.__class__.__name__

        MUSE_PRELOAD_ERROR = ""
        MUSE_PRELOAD_THREAD = threading.Thread(target=runner, daemon=True)
        MUSE_PRELOAD_THREAD.start()
        return True


def musetalk_worker_loaded_signatures() -> set[str]:
    with MUSE_WORKER_LOCK:
        cleanup_dead_musetalk_workers_locked()
        return set(MUSE_WORKERS.keys())


def musetalk_preload_status_payload() -> dict:
    loaded_signatures = musetalk_worker_loaded_signatures()
    avatars = []
    for group, avatar_video in configured_avatar_entries():
        avatar_signature = musetalk_avatar_signature(avatar_video)
        avatars.append(
            {
                "group": group,
                "avatar_path": str(avatar_video),
                "avatar_signature": avatar_signature,
                "cache_ready": musetalk_avatar_cache_ready(avatar_video),
                "worker_alive": avatar_signature in loaded_signatures,
                "loaded_in_vram": avatar_signature in loaded_signatures,
            }
        )
    return {
        "persistent_worker_enabled": settings.MUSE_TALK_PERSISTENT_WORKER,
        "multi_avatar_pool_enabled": settings.MUSE_TALK_MULTI_AVATAR_POOL,
        "max_vram_avatars": max_musetalk_vram_avatars(),
        "preload_targets": [str(path) for path in preload_target_avatar_videos()],
        "active_workers": len(loaded_signatures),
        "preload_running": bool(MUSE_PRELOAD_THREAD and MUSE_PRELOAD_THREAD.is_alive()),
        "preload_error": MUSE_PRELOAD_ERROR,
        "avatars": avatars,
    }


def kickoff_model_warmup():
    global MUSE_WARMUP_STARTED, SADTALKER_WARMUP_STARTED
    should_start_preload = False

    if settings.MUSE_TALK_PERSISTENT_WORKER and not MUSE_WARMUP_STARTED:
        with MUSE_WORKER_LOCK:
            if not MUSE_WARMUP_STARTED:
                MUSE_WARMUP_STARTED = True
                should_start_preload = True

    if should_start_preload:
        start_musetalk_preload_thread()

    if not SADTALKER_WARMUP_STARTED:
        SADTALKER_WARMUP_STARTED = True

        def warmup_sadtalker():
            try:
                resolve_sadtalker_script()
                resolve_sadtalker_python()
            except Exception:
                pass

        threading.Thread(target=warmup_sadtalker, daemon=True).start()


def switch_cache_dir() -> Path:
    cache_dir = Path(settings.MEDIA_ROOT) / "switch_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cached_switch_clip_url(current_group: str, target_group: str, switch_text: str) -> str:
    source_avatar = resolve_avatar_video_for_group(current_group)
    source_speaker = tts_speaker_for_group(current_group)
    digest = hashlib.sha1(f"{current_group}|{source_speaker}|{switch_text}".encode("utf-8")).hexdigest()[:16]
    cache_dir = switch_cache_dir()
    audio_path = cache_dir / f"switch_{digest}.mp3"
    video_path = cache_dir / f"switch_{digest}.mp4"

    if video_path.exists():
        return f"{settings.MEDIA_URL}switch_cache/{video_path.name}"

    with SWITCH_CACHE_LOCK:
        if video_path.exists():
            return f"{settings.MEDIA_URL}switch_cache/{video_path.name}"
        if not audio_path.exists():
            synthesize_tts(
                switch_text,
                audio_path,
                "en",
                request_id=f"switch_{digest}",
                speaker_override=source_speaker,
            )
        run_musetalk_lipsync(source_avatar, audio_path, video_path)
    return f"{settings.MEDIA_URL}switch_cache/{video_path.name}"
