"""Bot API test transport, used with real PTB Update dispatch and PostgreSQL."""

import json
import time
from html import unescape
import re

from telegram.request import BaseRequest


class TelegramAPI(BaseRequest):
    @property
    def read_timeout(self):
        return 5

    def __init__(self):
        self.calls = []
        self.messages = {}
        self.memberships = {}
        self.counter = 0

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(
        self, url, method, request_data=None, write_timeout=BaseRequest.DEFAULT_NONE, **kwargs
    ):
        endpoint = url.rsplit("/", 1)[-1]
        data = request_data.parameters if request_data else {}
        self.calls.append((endpoint, data))
        result = True
        if endpoint == "getMe":
            result = {
                "id": 999,
                "is_bot": True,
                "first_name": "LibraryBot",
                "username": "TestLibraryBot",
            }
        elif endpoint == "getChatMember":
            uid, gid = int(data["user_id"]), int(data["chat_id"])
            status = self.memberships.get((gid, uid), "administrator" if uid == 999 else "member")
            result = {
                "status": status,
                "user": {"id": uid, "is_bot": uid == 999, "first_name": "Reader"},
            }
            if status == "administrator":
                result.update(
                    can_be_edited=False,
                    is_anonymous=False,
                    can_manage_chat=True,
                    can_delete_messages=True,
                    can_manage_video_chats=True,
                    can_restrict_members=True,
                    can_promote_members=True,
                    can_change_info=True,
                    can_invite_users=True,
                    can_post_stories=True,
                    can_edit_stories=True,
                    can_delete_stories=True,
                )
        elif endpoint.startswith(("send", "editMessage")):
            gid = int(data["chat_id"])
            editing = endpoint.startswith("edit")
            if not editing:
                self.counter += 1
            mid = int(data["message_id"]) if editing else self.counter
            result = {
                "message_id": mid,
                "date": int(time.time()),
                "from": {"id": 999, "is_bot": True, "first_name": "LibraryBot"},
                "chat": {
                    "id": gid,
                    "type": "private" if gid > 0 else "supergroup",
                    "title": "Test group",
                },
            }
            media = data.get("media", {})
            if isinstance(media, str):
                media = json.loads(media)
            text = data.get("text") or data.get("caption") or media.get("caption") or ""
            photo = endpoint == "sendPhoto" or endpoint == "editMessageMedia"
            visible = unescape(re.sub(r"<[^>]+>", "", text))
            # Telegram limits count UTF-16 code units after entity parsing.
            limit = 1024 if photo else 4096
            assert len(visible.encode("utf-16-le")) // 2 <= limit, (endpoint, len(visible), text)
            result["caption" if photo else "text"] = text
            if photo:
                result["photo"] = [
                    {
                        "file_id": "test-photo",
                        "file_unique_id": "test-photo",
                        "width": 900,
                        "height": 900,
                    }
                ]
            markup = data.get("reply_markup")
            if isinstance(markup, str):
                markup = json.loads(markup)
            if markup:
                result["reply_markup"] = markup
            self.messages[(gid, mid)] = result
        elif endpoint == "deleteMessage":
            self.messages.pop((int(data["chat_id"]), int(data["message_id"])), None)
        return 200, json.dumps({"ok": True, "result": result}).encode()
