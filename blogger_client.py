"""Google Blogger API v3 OAuth 2.0 인증 및 포스팅 클라이언트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/blogger"]


class BloggerClient:
    """OAuth 2.0 인증을 관리하고 Blogger API v3를 호출하는 클라이언트."""

    def __init__(
        self,
        blog_id: str | None = None,
        client_secret_path: Path | None = None,
        token_path: Path | None = None,
    ) -> None:
        self.blog_id = blog_id or config.BLOGGER_BLOG_ID
        self.client_secret_path = client_secret_path or config.CLIENT_SECRET_PATH
        self.token_path = token_path or config.TOKEN_FILE
        if not self.blog_id:
            raise ValueError("BLOGGER_BLOG_ID가 설정되어 있지 않습니다.")
        self._service: Any = None

    def get_credentials(self) -> Credentials:
        """저장된 token.json을 재사용하거나 브라우저 OAuth 로그인으로 새로 발급받는다."""
        creds: Credentials | None = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request(session=config.create_http_session()))
            else:
                if not self.client_secret_path or not self.client_secret_path.exists():
                    raise FileNotFoundError(
                        f"OAuth 클라이언트 시크릿 파일을 찾을 수 없습니다: {self.client_secret_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), SCOPES
                )
                config.mount_system_ssl(flow.oauth2session)
                creds = flow.run_local_server(port=0)

            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds

    @property
    def service(self) -> Any:
        """인증된 Blogger v3 서비스 리소스를 지연 생성한다."""
        if self._service is None:
            creds = self.get_credentials()
            http = httplib2.Http(ca_certs=config.get_ca_bundle_path())
            authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            self._service = build(
                "blogger", "v3", http=authorized_http, cache_discovery=False
            )
        return self._service

    def get_blog_info(self) -> dict[str, Any]:
        """연결된 블로그의 메타정보(이름, URL, 전체 글 수 등)를 조회한다."""
        return self.service.blogs().get(blogId=self.blog_id).execute()

    def list_posts(
        self, status: list[str] | None = None, max_results: int = 50
    ) -> list[dict[str, Any]]:
        """블로그의 포스트 목록을 조회한다."""
        target_status = status or ["LIVE", "DRAFT"]
        resp = (
            self.service.posts()
            .list(blogId=self.blog_id, status=target_status, maxResults=max_results)
            .execute()
        )
        return resp.get("items", [])

    def patch_post(
        self,
        post_id: str,
        labels: list[str] | None = None,
        title: str | None = None,
        html_content: str | None = None,
    ) -> dict[str, Any]:
        """기존 블로그 포스트의 라벨(카테고리), 제목 또는 본문을 부분 수정한다."""
        body: dict[str, Any] = {}
        if labels is not None:
            body["labels"] = labels
        if title is not None:
            body["title"] = title
        if html_content is not None:
            body["content"] = html_content
        return (
            self.service.posts()
            .patch(blogId=self.blog_id, postId=str(post_id), body=body)
            .execute()
        )

    def insert_post(
        self,
        title: str,
        html_content: str,
        labels: list[str] | None = None,
        is_draft: bool = True,
    ) -> dict[str, Any]:
        """블로그에 새 글을 임시저장 또는 즉시 발행한다."""
        body: dict[str, Any] = {
            "kind": "blogger#post",
            "blog": {"id": self.blog_id},
            "title": title,
            "content": html_content,
        }
        if labels:
            body["labels"] = labels

        return (
            self.service.posts()
            .insert(blogId=self.blog_id, body=body, isDraft=is_draft)
            .execute()
        )
