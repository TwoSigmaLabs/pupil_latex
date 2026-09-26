"""Document walking: which keys and values are content.

The LaTeX functions are for renderable text (questions, scripts,
explanations), not for ids, URLs, paths, timestamps or status enums.
Whole-payload sanitisation corrupted those in Backend #454 (AHS audio URLs
got `$ahs_<hex>$` injected). Every deep walker in this package uses these
two predicates.
"""

from __future__ import annotations

from typing import Any

NON_CONTENT_KEYS: frozenset[str] = frozenset(
    {
        # Identifiers (camelCase, snake_case and plain all lower to these)
        "_id", "id", "uuid", "objectid", "userid", "sessionid", "studentid",
        "teacherid", "classid", "schoolid", "institutionid", "assessmentid",
        "questionid", "submissionid", "attemptid", "taskid", "jobid",
        "chapterid", "lessonid", "remedyid", "gapid", "tcdid", "eventid",
        "templateid",
        # URLs / paths
        "url", "uri", "audiourl", "audio_file_url", "audiofileurl", "videourl",
        "imageurl", "fileurl", "thumbnailurl", "iconurl", "redirecturl", "path",
        "filepath", "blobname", "gcspath", "filename",
        # Auth / secrets
        "token", "accesstoken", "refreshtoken", "apikey", "secret", "password",
        "passwordhash",
        # Contact / PII
        "email", "phone", "mobile", "contact", "contactnumber",
        # Names / login
        "name", "username", "firstname", "lastname", "loginid",
        # Timestamps / dates
        "createdat", "updatedat", "submittedat", "startedat", "completedat",
        "duedate", "scheduledat", "scheduleddate", "timestamp", "dob",
        # Status / enums
        "role", "status", "type", "kind", "state", "mode",
        # In-class image fields: enum values like "ai_recreate" must not
        # become "$ai_recreate$".
        "imagesource", "imagesstatus", "diagramstatus", "diagramtype",
        "diagrammodel",
        # Class / school metadata ("10_A" must not become "$10_A$")
        "board", "grade", "section", "academicyear", "classname", "subject",
        "gradelevel", "grade_level", "classlevel",
        # Build / version
        "version", "revision", "imagesha", "buildid",
        # MIME
        "contenttype", "mimetype", "encoding",
        # Taxonomy lists: `{"tags": ["x_1"]}` must not become `$x_1$`
        "tags", "labels", "keywords",
    }
)  # fmt: skip

NON_CONTENT_KEY_SUFFIXES: tuple[str, ...] = (
    "_id", "_url", "_uri", "_path", "_filename", "_email", "_phone", "_at",
    "_date", "_time", "_token", "_secret", "_key", "_hash", "_sha", "_level",
)  # fmt: skip

URL_PREFIXES: tuple[str, ...] = ("http://", "https://", "gs://", "/api/", "/learn/")
FILE_EXTENSIONS: tuple[str, ...] = (
    ".wav", ".mp3", ".mp4", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".svg", ".ico",
)  # fmt: skip

# Fields that hold the model's RAW output or our own prompts — kept for
# provenance, never rendered. `audit_deep` skips them.
NOT_RENDERED_KEYS: frozenset[str] = frozenset(
    {
        "raw", "raw_response", "raw_output", "raw_text", "raw_content",
        "prompt", "system_prompt", "system_instruction", "error", "traceback",
    }
)  # fmt: skip


def is_non_content_key(key: Any) -> bool:
    """True for a dict key whose value must pass through untouched.

    Case-insensitive; `user_id`, `userId` and `userid` all match.
    """
    if not isinstance(key, str):
        return False
    k = key.lower().replace("-", "_")
    if k in NON_CONTENT_KEYS or k.replace("_", "") in NON_CONTENT_KEYS:
        return True
    return any(k.endswith(suffix) for suffix in NON_CONTENT_KEY_SUFFIXES)


def is_url_or_path_string(value: Any) -> bool:
    """True for strings shaped like URLs, API paths or media files."""
    if not isinstance(value, str) or not value:
        return False
    if value.startswith(URL_PREFIXES):
        return True
    return value.lower().endswith(FILE_EXTENSIONS)


def is_not_rendered_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower()
    return k in NOT_RENDERED_KEYS or k.endswith("_raw") or k.startswith("raw_")
