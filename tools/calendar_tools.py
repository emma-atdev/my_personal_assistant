"""Google Calendar API 툴 — 일정 조회 및 생성."""

import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@lru_cache(maxsize=1)
def _service() -> Any:
    """Google Calendar 서비스 클라이언트를 반환한다."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN 환경변수를 확인해주세요.")

    creds = Credentials(  # type: ignore[no-untyped-call]
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds)


def list_events(days: int = 7, max_results: int = 20) -> str:
    """앞으로 N일간의 Google Calendar 일정을 반환한다.

    Args:
        days: 조회할 일 수 (기본 7일)
        max_results: 최대 반환 개수 (기본 20)

    Returns:
        일정 목록 (날짜, 시간, 제목, 장소)
    """
    try:
        now = datetime.now(UTC)
        end = now + timedelta(days=days)

        events_result = (
            _service()
            .events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return f"앞으로 {days}일간 일정 없음"

        lines: list[str] = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            end_time = event["end"].get("dateTime", event["end"].get("date", ""))
            summary = event.get("summary", "(제목 없음)")
            location = event.get("location", "")

            # 날짜/시간 포맷
            try:
                start_dt = datetime.fromisoformat(start)
                if "T" in start:
                    time_str = start_dt.strftime("%m/%d(%a) %H:%M")
                    end_dt = datetime.fromisoformat(end_time)
                    time_str += f" ~ {end_dt.strftime('%H:%M')}"
                else:
                    time_str = start_dt.strftime("%m/%d(%a) 종일")
            except ValueError:
                time_str = start

            line = f"📅 {time_str} | {summary}"
            if location:
                line += f"\n   📍 {location}"
            lines.append(line)

        return "\n\n".join(lines)
    except HttpError as e:
        return f"Google Calendar API 오류: {e}"


def create_event(
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
) -> str:
    """Google Calendar에 일정을 생성한다.

    Args:
        title: 일정 제목
        start: 시작 시간 (ISO 형식, 예: "2026-03-25T14:00:00+09:00" 또는 "2026-03-25")
        end: 종료 시간 (ISO 형식, 예: "2026-03-25T15:00:00+09:00" 또는 "2026-03-26")
        description: 일정 설명 (선택)
        location: 장소 (선택)

    Returns:
        생성된 일정 링크
    """
    try:
        is_all_day = "T" not in start

        if is_all_day:
            event_body: dict[str, object] = {
                "summary": title,
                "start": {"date": start},
                "end": {"date": end},
            }
        else:
            event_body = {
                "summary": title,
                "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                "end": {"dateTime": end, "timeZone": "Asia/Seoul"},
            }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        event = _service().events().insert(calendarId="primary", body=event_body).execute()

        return f"일정 생성 완료: {event.get('htmlLink', '')}"
    except HttpError as e:
        return f"Google Calendar API 오류: {e}"


def get_today_schedule() -> str:
    """오늘 하루 일정을 반환한다.

    Returns:
        오늘 일정 목록
    """
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    try:
        events_result = (
            _service()
            .events()
            .list(
                calendarId="primary",
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return "오늘 일정 없음"

        lines: list[str] = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            summary = event.get("summary", "(제목 없음)")
            try:
                start_dt = datetime.fromisoformat(start)
                time_str = start_dt.strftime("%H:%M") if "T" in start else "종일"
            except ValueError:
                time_str = start
            lines.append(f"{time_str} {summary}")

        return "오늘 일정:\n" + "\n".join(lines)
    except HttpError as e:
        return f"Google Calendar API 오류: {e}"
