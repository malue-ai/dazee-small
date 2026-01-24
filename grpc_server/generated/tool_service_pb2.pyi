from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ChatRequest(_message.Message):
    __slots__ = ("message", "user_id", "conversation_id", "message_id", "stream", "background_tasks", "files", "variables", "agent_id")
    class VariablesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_TASKS_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    VARIABLES_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    message: str
    user_id: str
    conversation_id: str
    message_id: str
    stream: bool
    background_tasks: _containers.RepeatedScalarFieldContainer[str]
    files: _containers.RepeatedCompositeFieldContainer[FileReference]
    variables: _containers.ScalarMap[str, str]
    agent_id: str
    def __init__(self, message: _Optional[str] = ..., user_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., message_id: _Optional[str] = ..., stream: bool = ..., background_tasks: _Optional[_Iterable[str]] = ..., files: _Optional[_Iterable[_Union[FileReference, _Mapping]]] = ..., variables: _Optional[_Mapping[str, str]] = ..., agent_id: _Optional[str] = ...) -> None: ...

class FileReference(_message.Message):
    __slots__ = ("file_id", "file_url", "file_name")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    file_url: str
    file_name: str
    def __init__(self, file_id: _Optional[str] = ..., file_url: _Optional[str] = ..., file_name: _Optional[str] = ...) -> None: ...

class ChatResponse(_message.Message):
    __slots__ = ("code", "message", "task_id", "conversation_id", "status", "result")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    code: int
    message: str
    task_id: str
    conversation_id: str
    status: str
    result: str
    def __init__(self, code: _Optional[int] = ..., message: _Optional[str] = ..., task_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., status: _Optional[str] = ..., result: _Optional[str] = ...) -> None: ...

class ChatEvent(_message.Message):
    __slots__ = ("event_type", "data", "timestamp", "seq", "event_uuid")
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    EVENT_UUID_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    data: str
    timestamp: int
    seq: int
    event_uuid: str
    def __init__(self, event_type: _Optional[str] = ..., data: _Optional[str] = ..., timestamp: _Optional[int] = ..., seq: _Optional[int] = ..., event_uuid: _Optional[str] = ...) -> None: ...

class ReconnectRequest(_message.Message):
    __slots__ = ("session_id", "after_seq")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    AFTER_SEQ_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    after_seq: int
    def __init__(self, session_id: _Optional[str] = ..., after_seq: _Optional[int] = ...) -> None: ...

class ChatMockRequest(_message.Message):
    __slots__ = ("scenario", "delay_ms")
    SCENARIO_FIELD_NUMBER: _ClassVar[int]
    DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    scenario: str
    delay_ms: int
    def __init__(self, scenario: _Optional[str] = ..., delay_ms: _Optional[int] = ...) -> None: ...

class HealthCheckRequest(_message.Message):
    __slots__ = ("service",)
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    service: str
    def __init__(self, service: _Optional[str] = ...) -> None: ...

class HealthCheckResponse(_message.Message):
    __slots__ = ("status",)
    class ServingStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[HealthCheckResponse.ServingStatus]
        SERVING: _ClassVar[HealthCheckResponse.ServingStatus]
        NOT_SERVING: _ClassVar[HealthCheckResponse.ServingStatus]
        SERVICE_UNKNOWN: _ClassVar[HealthCheckResponse.ServingStatus]
    UNKNOWN: HealthCheckResponse.ServingStatus
    SERVING: HealthCheckResponse.ServingStatus
    NOT_SERVING: HealthCheckResponse.ServingStatus
    SERVICE_UNKNOWN: HealthCheckResponse.ServingStatus
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: HealthCheckResponse.ServingStatus
    def __init__(self, status: _Optional[_Union[HealthCheckResponse.ServingStatus, str]] = ...) -> None: ...

class SessionStatusRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class SessionStatusResponse(_message.Message):
    __slots__ = ("session_id", "user_id", "conversation_id", "message_id", "status", "last_event_seq", "start_time", "last_heartbeat", "progress", "total_turns", "message_preview")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_EVENT_SEQ_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TURNS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_PREVIEW_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    user_id: str
    conversation_id: str
    message_id: str
    status: str
    last_event_seq: int
    start_time: str
    last_heartbeat: str
    progress: float
    total_turns: int
    message_preview: str
    def __init__(self, session_id: _Optional[str] = ..., user_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., message_id: _Optional[str] = ..., status: _Optional[str] = ..., last_event_seq: _Optional[int] = ..., start_time: _Optional[str] = ..., last_heartbeat: _Optional[str] = ..., progress: _Optional[float] = ..., total_turns: _Optional[int] = ..., message_preview: _Optional[str] = ...) -> None: ...

class SessionEventsRequest(_message.Message):
    __slots__ = ("session_id", "after_id", "limit")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    AFTER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    after_id: int
    limit: int
    def __init__(self, session_id: _Optional[str] = ..., after_id: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class SessionEventsResponse(_message.Message):
    __slots__ = ("session_id", "events", "total", "has_more", "last_event_id")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    LAST_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    events: _containers.RepeatedCompositeFieldContainer[ChatEvent]
    total: int
    has_more: bool
    last_event_id: int
    def __init__(self, session_id: _Optional[str] = ..., events: _Optional[_Iterable[_Union[ChatEvent, _Mapping]]] = ..., total: _Optional[int] = ..., has_more: bool = ..., last_event_id: _Optional[int] = ...) -> None: ...

class UserSessionsRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class UserSessionsResponse(_message.Message):
    __slots__ = ("user_id", "sessions", "total")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    sessions: _containers.RepeatedCompositeFieldContainer[SessionInfo]
    total: int
    def __init__(self, user_id: _Optional[str] = ..., sessions: _Optional[_Iterable[_Union[SessionInfo, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class SessionInfo(_message.Message):
    __slots__ = ("session_id", "conversation_id", "message_id", "status", "progress", "start_time", "message_preview")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_PREVIEW_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    conversation_id: str
    message_id: str
    status: str
    progress: float
    start_time: str
    message_preview: str
    def __init__(self, session_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., message_id: _Optional[str] = ..., status: _Optional[str] = ..., progress: _Optional[float] = ..., start_time: _Optional[str] = ..., message_preview: _Optional[str] = ...) -> None: ...

class StopSessionRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class StopSessionResponse(_message.Message):
    __slots__ = ("session_id", "status", "stopped_at")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STOPPED_AT_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    status: str
    stopped_at: str
    def __init__(self, session_id: _Optional[str] = ..., status: _Optional[str] = ..., stopped_at: _Optional[str] = ...) -> None: ...

class EndSessionRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class EndSessionResponse(_message.Message):
    __slots__ = ("session_id", "summary")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    summary: str
    def __init__(self, session_id: _Optional[str] = ..., summary: _Optional[str] = ...) -> None: ...

class ListSessionsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListSessionsResponse(_message.Message):
    __slots__ = ("sessions", "total")
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    sessions: _containers.RepeatedCompositeFieldContainer[SessionInfo]
    total: int
    def __init__(self, sessions: _Optional[_Iterable[_Union[SessionInfo, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class ToolRequest(_message.Message):
    __slots__ = ("tool_name", "input_data", "invocation_id", "conversation_id", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
    INPUT_DATA_FIELD_NUMBER: _ClassVar[int]
    INVOCATION_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    tool_name: str
    input_data: str
    invocation_id: str
    conversation_id: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, tool_name: _Optional[str] = ..., input_data: _Optional[str] = ..., invocation_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ToolResponse(_message.Message):
    __slots__ = ("success", "result", "error", "execution_time_ms")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    result: str
    error: str
    execution_time_ms: int
    def __init__(self, success: bool = ..., result: _Optional[str] = ..., error: _Optional[str] = ..., execution_time_ms: _Optional[int] = ...) -> None: ...

class ToolChunk(_message.Message):
    __slots__ = ("chunk_type", "content", "is_final")
    CHUNK_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    IS_FINAL_FIELD_NUMBER: _ClassVar[int]
    chunk_type: str
    content: str
    is_final: bool
    def __init__(self, chunk_type: _Optional[str] = ..., content: _Optional[str] = ..., is_final: bool = ...) -> None: ...

class ToolBatchRequest(_message.Message):
    __slots__ = ("requests",)
    REQUESTS_FIELD_NUMBER: _ClassVar[int]
    requests: _containers.RepeatedCompositeFieldContainer[ToolRequest]
    def __init__(self, requests: _Optional[_Iterable[_Union[ToolRequest, _Mapping]]] = ...) -> None: ...

class ToolBatchResponse(_message.Message):
    __slots__ = ("responses",)
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[ToolResponse]
    def __init__(self, responses: _Optional[_Iterable[_Union[ToolResponse, _Mapping]]] = ...) -> None: ...

class AgentTaskRequest(_message.Message):
    __slots__ = ("task_id", "user_input", "conversation_id", "user_id", "context")
    class ContextEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    USER_INPUT_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    user_input: str
    conversation_id: str
    user_id: str
    context: _containers.ScalarMap[str, str]
    def __init__(self, task_id: _Optional[str] = ..., user_input: _Optional[str] = ..., conversation_id: _Optional[str] = ..., user_id: _Optional[str] = ..., context: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AgentTaskResponse(_message.Message):
    __slots__ = ("success", "result", "error", "turns", "execution_time_ms")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    TURNS_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    result: str
    error: str
    turns: int
    execution_time_ms: int
    def __init__(self, success: bool = ..., result: _Optional[str] = ..., error: _Optional[str] = ..., turns: _Optional[int] = ..., execution_time_ms: _Optional[int] = ...) -> None: ...

class AgentTaskEvent(_message.Message):
    __slots__ = ("event_type", "data", "timestamp")
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    data: str
    timestamp: int
    def __init__(self, event_type: _Optional[str] = ..., data: _Optional[str] = ..., timestamp: _Optional[int] = ...) -> None: ...

class AgentStatusRequest(_message.Message):
    __slots__ = ("agent_id", "conversation_id")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    conversation_id: str
    def __init__(self, agent_id: _Optional[str] = ..., conversation_id: _Optional[str] = ...) -> None: ...

class AgentStatusResponse(_message.Message):
    __slots__ = ("status", "current_step", "progress", "active_tools")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_STEP_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_TOOLS_FIELD_NUMBER: _ClassVar[int]
    status: str
    current_step: str
    progress: int
    active_tools: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, status: _Optional[str] = ..., current_step: _Optional[str] = ..., progress: _Optional[int] = ..., active_tools: _Optional[_Iterable[str]] = ...) -> None: ...

class SandboxStatusRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SandboxStatusResponse(_message.Message):
    __slots__ = ("conversation_id", "sandbox_id", "e2b_sandbox_id", "status", "stack", "preview_url", "active_project_path", "active_project_stack", "created_at", "last_active_at")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    SANDBOX_ID_FIELD_NUMBER: _ClassVar[int]
    E2B_SANDBOX_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STACK_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_URL_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PROJECT_PATH_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PROJECT_STACK_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_ACTIVE_AT_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    sandbox_id: str
    e2b_sandbox_id: str
    status: str
    stack: str
    preview_url: str
    active_project_path: str
    active_project_stack: str
    created_at: str
    last_active_at: str
    def __init__(self, conversation_id: _Optional[str] = ..., sandbox_id: _Optional[str] = ..., e2b_sandbox_id: _Optional[str] = ..., status: _Optional[str] = ..., stack: _Optional[str] = ..., preview_url: _Optional[str] = ..., active_project_path: _Optional[str] = ..., active_project_stack: _Optional[str] = ..., created_at: _Optional[str] = ..., last_active_at: _Optional[str] = ...) -> None: ...

class SandboxInitRequest(_message.Message):
    __slots__ = ("conversation_id", "user_id", "stack")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    STACK_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    user_id: str
    stack: str
    def __init__(self, conversation_id: _Optional[str] = ..., user_id: _Optional[str] = ..., stack: _Optional[str] = ...) -> None: ...

class SandboxPauseRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SandboxResumeRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SandboxKillRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SandboxOperationResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class SandboxRunProjectRequest(_message.Message):
    __slots__ = ("conversation_id", "project_path", "stack")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    PROJECT_PATH_FIELD_NUMBER: _ClassVar[int]
    STACK_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    project_path: str
    stack: str
    def __init__(self, conversation_id: _Optional[str] = ..., project_path: _Optional[str] = ..., stack: _Optional[str] = ...) -> None: ...

class SandboxRunProjectResponse(_message.Message):
    __slots__ = ("success", "preview_url", "message", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_URL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    preview_url: str
    message: str
    error: str
    def __init__(self, success: bool = ..., preview_url: _Optional[str] = ..., message: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class SandboxStopProjectRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SandboxLogsRequest(_message.Message):
    __slots__ = ("conversation_id", "lines")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    LINES_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    lines: int
    def __init__(self, conversation_id: _Optional[str] = ..., lines: _Optional[int] = ...) -> None: ...

class SandboxLogsResponse(_message.Message):
    __slots__ = ("logs",)
    LOGS_FIELD_NUMBER: _ClassVar[int]
    logs: str
    def __init__(self, logs: _Optional[str] = ...) -> None: ...

class SandboxCommandRequest(_message.Message):
    __slots__ = ("conversation_id", "command", "timeout")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    command: str
    timeout: int
    def __init__(self, conversation_id: _Optional[str] = ..., command: _Optional[str] = ..., timeout: _Optional[int] = ...) -> None: ...

class SandboxCommandResponse(_message.Message):
    __slots__ = ("success", "exit_code", "stdout", "stderr", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    STDERR_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    error: str
    def __init__(self, success: bool = ..., exit_code: _Optional[int] = ..., stdout: _Optional[str] = ..., stderr: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class SandboxListFilesRequest(_message.Message):
    __slots__ = ("conversation_id", "path", "tree")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    TREE_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    path: str
    tree: bool
    def __init__(self, conversation_id: _Optional[str] = ..., path: _Optional[str] = ..., tree: bool = ...) -> None: ...

class SandboxFileInfo(_message.Message):
    __slots__ = ("path", "name", "type", "size", "modified_at", "children")
    PATH_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    MODIFIED_AT_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    path: str
    name: str
    type: str
    size: int
    modified_at: str
    children: _containers.RepeatedCompositeFieldContainer[SandboxFileInfo]
    def __init__(self, path: _Optional[str] = ..., name: _Optional[str] = ..., type: _Optional[str] = ..., size: _Optional[int] = ..., modified_at: _Optional[str] = ..., children: _Optional[_Iterable[_Union[SandboxFileInfo, _Mapping]]] = ...) -> None: ...

class SandboxListFilesResponse(_message.Message):
    __slots__ = ("conversation_id", "files", "source")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    files: _containers.RepeatedCompositeFieldContainer[SandboxFileInfo]
    source: str
    def __init__(self, conversation_id: _Optional[str] = ..., files: _Optional[_Iterable[_Union[SandboxFileInfo, _Mapping]]] = ..., source: _Optional[str] = ...) -> None: ...
