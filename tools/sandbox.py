"""DockerSandbox — BaseSandbox를 상속한 Docker 기반 격리 실행 환경."""

import subprocess
import uuid

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

DEFAULT_TIMEOUT = 30  # seconds
MAX_OUTPUT_BYTES = 50_000
DOCKER_IMAGE = "python:3.13-slim"


class DockerSandbox(BaseSandbox):
    """Docker 컨테이너 기반 격리 샌드박스.

    persistent 컨테이너(sleep infinity)를 유지하며 execute()로 명령을 실행합니다.
    호스트 파일시스템, 환경변수, API 키에 접근할 수 없습니다.

    보안 설정:
    - --network=none: 인터넷 완전 차단
    - --memory=512m: 메모리 제한
    - --cpus=0.5: CPU 제한
    - 호스트 볼륨 미마운트: 호스트 파일 접근 불가
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._default_timeout = timeout
        self._sandbox_id = f"docker-{uuid.uuid4().hex[:8]}"

        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--network=none",
                "--memory=512m",
                "--cpus=0.5",
                "--name",
                self._sandbox_id,
                DOCKER_IMAGE,
                "sleep",
                "infinity",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Docker 컨테이너 시작 실패: {result.stderr.strip()}\nDocker Desktop이 실행 중인지 확인해 주세요."
            )
        self._container_id = result.stdout.strip()

    @property
    def id(self) -> str:
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """컨테이너 내에서 셸 명령을 실행한다."""
        effective_timeout = timeout if timeout is not None else self._default_timeout

        try:
            result = subprocess.run(
                ["docker", "exec", self._container_id, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"오류: {effective_timeout}초 초과로 실행이 종료되었습니다.",
                exit_code=124,
            )
        except FileNotFoundError:
            return ExecuteResponse(
                output="오류: Docker가 설치되어 있지 않거나 실행 중이 아닙니다.",
                exit_code=1,
            )

        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            stderr_lines = result.stderr.strip().split("\n")
            parts.extend(f"[stderr] {line}" for line in stderr_lines)

        output = "\n".join(parts) if parts else "<no output>"

        truncated = False
        if len(output) > MAX_OUTPUT_BYTES:
            output = output[:MAX_OUTPUT_BYTES] + f"\n\n... {MAX_OUTPUT_BYTES}바이트 초과로 잘렸습니다."
            truncated = True

        return ExecuteResponse(
            output=output,
            exit_code=result.returncode,
            truncated=truncated,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """파일을 컨테이너 안으로 복사한다."""
        import tempfile
        from pathlib import Path

        responses: list[FileUploadResponse] = []
        for dest_path, content in files:
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                # 대상 디렉토리 생성
                parent = str(Path(dest_path).parent)
                subprocess.run(
                    ["docker", "exec", self._container_id, "mkdir", "-p", parent],
                    check=False,
                    capture_output=True,
                )
                subprocess.run(
                    ["docker", "cp", tmp_path, f"{self._container_id}:{dest_path}"],
                    check=True,
                    capture_output=True,
                )
                Path(tmp_path).unlink(missing_ok=True)
                responses.append(FileUploadResponse(path=dest_path))
            except subprocess.CalledProcessError:
                responses.append(FileUploadResponse(path=dest_path, error="permission_denied"))
            except Exception:  # noqa: BLE001
                responses.append(FileUploadResponse(path=dest_path, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """컨테이너에서 파일을 가져온다."""
        import tempfile
        from pathlib import Path

        responses: list[FileDownloadResponse] = []
        for src_path in paths:
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name

                result = subprocess.run(
                    ["docker", "cp", f"{self._container_id}:{src_path}", tmp_path],
                    capture_output=True,
                    check=False,
                )
                if result.returncode != 0:
                    responses.append(FileDownloadResponse(path=src_path, error="file_not_found"))
                    continue

                content = Path(tmp_path).read_bytes()
                Path(tmp_path).unlink(missing_ok=True)
                responses.append(FileDownloadResponse(path=src_path, content=content))
            except Exception:  # noqa: BLE001
                responses.append(FileDownloadResponse(path=src_path, error="invalid_path"))
        return responses

    def close(self) -> None:
        """컨테이너를 종료한다."""
        subprocess.run(
            ["docker", "stop", self._container_id],
            capture_output=True,
            check=False,
        )

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass
