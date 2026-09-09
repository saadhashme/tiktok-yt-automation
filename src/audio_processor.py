import os
import glob
import shutil
import subprocess
import wave
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is installed by the workflow,
    # but this module must not crash on import if it's ever missing (e.g. a
    # local run outside the CI environment); the quality check is skipped.
    np = None


def _find_default_music_path() -> str:
    """Locates the bundled background-music asset regardless of filename
    case. GitHub's web upload UI can keep an uppercase extension (e.g.
    background_music.MP3), and Linux filesystems (GitHub Actions runners)
    are case-sensitive, so a hardcoded lowercase '.mp3' path can silently
    miss the file. This scans the assets directory for anything named
    'background_music.*' and falls back to the lowercase default path if
    nothing is found (so a clear "file not found" message is still logged
    instead of a mismatch nobody notices)."""
    assets_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
    )
    fallback = os.path.join(assets_dir, "background_music.mp3")
    try:
        for name in os.listdir(assets_dir):
            if name.lower().startswith("background_music."):
                return os.path.join(assets_dir, name)
    except OSError:
        pass
    return fallback


class AudioProcessor:
    """Strips the TikTok source video's original background music (a common
    cause of YouTube Content ID copyright claims/blocks) while preserving the
    speaker's voice, then lays a fixed, owned background track underneath at
    a low, unobtrusive volume for the full length of the clip.

    Voice isolation is done with Demucs (AI source separation). If Demucs is
    unavailable or fails for any reason, this falls back to keeping the
    original audio (so the upload is never blocked by an audio processing
    failure) rather than raising.
    """

    DEFAULT_MUSIC_PATH = _find_default_music_path()
    # The bundled track is already pre-edited/mixed at a low background
    # level, so it is looped/trimmed/faded as-is with no extra attenuation
    # here (a second volume cut on top of an already-quiet source would
    # make it too faint under the voice).
    MUSIC_VOLUME = 1.0
    DEMUCS_TIMEOUT_SECONDS = 280
    # Minimum fraction of near-silent windows an isolated-vocals track must
    # show to be trusted as genuinely free of the original background music.
    # Below this, the caller should NOT treat the audio as copyright-safe.
    MIN_CLEAN_SILENT_RATIO = 0.15

    def __init__(self, music_path: Optional[str] = None):
        self.music_path = music_path or self.DEFAULT_MUSIC_PATH

    def _get_duration(self, file_path: str) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"ffprobe duration check failed: {e}")
            return 0.0

    def _isolate_vocals(self, audio_path: str, workdir: str) -> Optional[str]:
        """Runs Demucs two-stem separation and returns the path to the
        isolated vocals track, or None if unavailable/failed."""
        if not shutil.which("demucs"):
            print("demucs not installed; skipping voice isolation.")
            return None

        cmd = ["demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", workdir, audio_path]
        try:
            subprocess.run(
                cmd, check=True, capture_output=True, text=True,
                timeout=self.DEMUCS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            print("Demucs voice isolation timed out; falling back to original audio.")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Demucs voice isolation failed: {e.stderr}; falling back to original audio.")
            return None
        except Exception as e:
            print(f"Demucs voice isolation error: {e}; falling back to original audio.")
            return None

        stem = os.path.splitext(os.path.basename(audio_path))[0]
        matches = glob.glob(os.path.join(workdir, "*", stem, "vocals.wav"))
        if not matches:
            print("Demucs ran but no vocals.wav output was found; falling back to original audio.")
            return None
        return matches[0]

    def _measure_isolation_quality(self, vocals_path: str) -> Optional[float]:
        """Objective sanity check on how clean the Demucs vocal isolation
        actually is. Demucs completing without an error only means the
        pipeline ran, not that the original background music is genuinely
        gone -- AI source separation on short, compressed, music-forward
        clips can leave the music audibly bleeding through the 'vocals'
        stem. Real speech naturally has quiet gaps (breaths, pauses between
        phrases); continuous background music does not. This measures the
        fraction of short windows in the isolated track that are
        near-silent relative to its own peak level. A low fraction is a
        signal that background music likely survived the separation, even
        though nothing failed or logged an error. This is a heuristic, not
        a certainty -- it exists so a "succeeded" log line is never trusted
        as proof the audio is actually clean.
        """
        if np is None:
            print("Audio QC: numpy unavailable; skipping isolation quality check.")
            return None
        try:
            with wave.open(vocals_path, "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                frame_rate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
        except Exception as e:
            print(f"Audio QC: could not read {vocals_path} for quality check: {e}")
            return None

        if sample_width != 2:
            print("Audio QC: unexpected sample width; skipping quality check.")
            return None

        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels)[:, 0]

        window = max(1, int(frame_rate * 0.05))  # 50ms windows
        n_windows = len(samples) // window
        if n_windows < 2:
            print("Audio QC: clip too short for a meaningful quality check.")
            return None

        trimmed = samples[: n_windows * window].reshape(n_windows, window)
        rms = np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1))
        peak = max(1.0, float(np.max(np.abs(samples))))
        threshold = peak * 0.01  # roughly -40 dBFS relative to this track's own peak
        silent_ratio = float(np.mean(rms < threshold))

        verdict = "looks clean" if silent_ratio >= self.MIN_CLEAN_SILENT_RATIO else "WARNING: likely still has original music bleeding through"
        print(
            f"Audio QC: {silent_ratio * 100:.1f}% of isolated-vocal windows are "
            f"near-silent (~-40dBFS off this track's own peak) -> {verdict}. "
            f"(Typical short-form speech has noticeable quiet gaps between "
            f"phrases; continuous background music does not.)"
        )
        return silent_ratio

    def _apply_noise_gate(self, vocals_path: str, out_path: str) -> bool:
        """Applies a noise gate to the isolated vocals track to suppress
        low-level residual background-music bleed-through in the quiet gaps
        between phrases (Demucs separation is not always perfectly clean).
        Attenuates rather than hard-mutes quiet passages, so soft speech
        isn't chopped off. Returns False (caller keeps the ungated track) if
        the gate step itself fails for any reason."""
        cmd = [
            "ffmpeg", "-y", "-i", vocals_path,
            "-af", "agate=threshold=0.025:ratio=9:attack=5:release=200:range=0.05",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Noise gate on isolated vocals failed: {e.stderr}; using ungated vocals.")
            return False

    def _prepare_music_bed(self, duration: float, out_path: str) -> bool:
        """Loops/trims the fixed background track to exactly `duration`
        seconds at a low background volume, with a short fade in/out."""
        if not os.path.exists(self.music_path):
            print(f"Background music file not found at {self.music_path}; skipping music bed.")
            return False

        fade_out_start = max(duration - 1, 0)
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", self.music_path,
            "-t", str(duration),
            "-af", (
                f"volume={self.MUSIC_VOLUME},"
                f"afade=t=in:st=0:d=1,"
                f"afade=t=out:st={fade_out_start}:d=1"
            ),
            "-ac", "2", "-ar", "44100",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Preparing background music bed failed: {e.stderr}")
            return False

    def replace_background_music(self, video_path: str) -> "tuple[str, bool]":
        """Returns (new_video_path, is_copyright_safe).

        is_copyright_safe is only True when the original background music
        was verifiably (not just apparently) removed: Demucs separation
        succeeded, a noise gate was applied to suppress residual bleed in
        quiet gaps, and the objective Audio QC check confirms the result
        actually looks like isolated speech rather than continuous
        background audio. A "Demucs didn't error out" success message is
        NOT enough on its own to mark a video safe -- that was verified
        false against real uploads, where the isolation completed without
        error but still left the original music clearly audible.

        Never raises: any failure along the way falls back to returning the
        original, unmodified video (marked not copyright-safe) so a
        music-processing problem never crashes the run -- but the caller is
        responsible for not treating an unsafe result as safe to publish.
        """
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            print("ffmpeg/ffprobe not available; skipping background music replacement.")
            return video_path, False

        duration = self._get_duration(video_path)
        if duration <= 0:
            print("Could not determine video duration; skipping background music replacement.")
            return video_path, False

        workdir = video_path + "_audio_work"
        os.makedirs(workdir, exist_ok=True)
        extracted_audio = os.path.join(workdir, "original_audio.wav")
        music_bed = os.path.join(workdir, "music_bed.wav")
        mixed_audio = os.path.join(workdir, "mixed_audio.wav")
        gated_vocals = os.path.join(workdir, "vocals_gated.wav")
        output_path = video_path.replace(".mp4", "_remixed.mp4")

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
                 "-ar", "44100", "-ac", "2", extracted_audio],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Extracting original audio failed: {e.stderr}; skipping background music replacement.")
            shutil.rmtree(workdir, ignore_errors=True)
            return video_path, False

        has_music_bed = self._prepare_music_bed(duration, music_bed)
        vocals_path = self._isolate_vocals(extracted_audio, workdir)
        is_clean = False

        try:
            if vocals_path and has_music_bed:
                # Gate the isolated vocals to suppress residual background
                # music bleeding through the quiet gaps, then objectively
                # measure whether the result actually looks clean rather
                # than trusting that Demucs simply didn't error out.
                gate_ok = self._apply_noise_gate(vocals_path, gated_vocals)
                voice_for_mix = gated_vocals if gate_ok else vocals_path
                silent_ratio = self._measure_isolation_quality(voice_for_mix)
                is_clean = silent_ratio is not None and silent_ratio >= self.MIN_CLEAN_SILENT_RATIO

                if is_clean:
                    print("Voice isolated and verified clean; mixing with replacement background music.")
                else:
                    print("WARNING: isolated vocals did not pass the copyright-safety audio check "
                          "(original background music likely still audible). This result will be "
                          "treated as NOT copyright-safe by the caller.")

                filter_complex = (
                    "[0:a]volume=1.0[voice];"
                    "[1:a]volume=1.0[music];"
                    "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
                cmd = ["ffmpeg", "-y", "-i", voice_for_mix, "-i", music_bed,
                       "-filter_complex", filter_complex, "-map", "[aout]", mixed_audio]
            elif has_music_bed:
                # Voice isolation unavailable/failed: keep the original audio
                # (still carries the copyrighted music) but flag it loudly so
                # it's easy to spot in the run log, and still add our track.
                print("WARNING: voice isolation unavailable this run; original background music "
                      "was NOT removed (copyright risk remains). Falling back to layering the "
                      "replacement music under the untouched original audio.")
                filter_complex = (
                    "[0:a]volume=1.0[orig];"
                    "[1:a]volume=1.0[music];"
                    "[orig][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
                cmd = ["ffmpeg", "-y", "-i", extracted_audio, "-i", music_bed,
                       "-filter_complex", filter_complex, "-map", "[aout]", mixed_audio]
            else:
                print("No usable background music bed; leaving original audio untouched.")
                shutil.rmtree(workdir, ignore_errors=True)
                return video_path, False

            subprocess.run(cmd, check=True, capture_output=True, text=True)

            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-i", mixed_audio,
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                 "-shortest", output_path],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Background music replacement failed: {e.stderr}; uploading with original audio.")
            shutil.rmtree(workdir, ignore_errors=True)
            return video_path, False

        shutil.rmtree(workdir, ignore_errors=True)
        os.remove(video_path)
        return output_path, is_clean
