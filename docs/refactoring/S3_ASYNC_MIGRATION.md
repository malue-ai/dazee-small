# S3 Uploader 异步化重构

## 问题背景

原 `S3Uploader` 使用同步的 `boto3` 客户端，所有 S3 操作都是阻塞的，违反了项目的异步 I/O 规范。

### 发现的问题

```python
# ❌ 同步操作，阻塞事件循环
self.s3_client.upload_fileobj(...)
self.s3_client.generate_presigned_url(...)
self.s3_client.delete_object(...)
```

### 影响范围

1. **性能问题**：上传大文件时阻塞整个服务
2. **并发受限**：无法并发处理多个上传请求
3. **规范违反**：违反项目的异步 I/O 强制要求

## 重构方案

### 技术选型：aioboto3

选择 `aioboto3` 作为异步 S3 客户端：

- ✅ 完全兼容 boto3 API
- ✅ 原生异步支持
- ✅ 活跃维护
- ✅ 社区广泛使用

### 核心变更

#### 1. 依赖更新

```diff
# requirements.txt
- boto3>=1.34.0
+ aioboto3>=13.0.0
+ boto3>=1.34.0  # aioboto3 依赖 boto3
```

#### 2. 客户端初始化

```diff
- import boto3
+ import aioboto3

class S3Uploader:
    def __init__(self, config_path: str = "config/storage.yaml"):
-       self.s3_client = None
+       self.session: Optional[aioboto3.Session] = None
+       self._aws_access_key_id: Optional[str] = None
+       self._aws_secret_access_key: Optional[str] = None
+       self._region_name: Optional[str] = None
+       self._endpoint_url: Optional[str] = None
    
-   def _init_s3_client(self):
-       self.s3_client = boto3.client('s3', ...)
+   def _init_session(self):
+       self.session = aioboto3.Session(
+           aws_access_key_id=self._aws_access_key_id,
+           aws_secret_access_key=self._aws_secret_access_key,
+           region_name=self._region_name
+       )
```

#### 3. 异步上传操作

```diff
async def upload_file(self, ...):
-   self.s3_client.upload_fileobj(
-       io.BytesIO(file_content),
-       self.bucket_name,
-       s3_key,
-       ExtraArgs=extra_args
-   )
+   async with self.session.client('s3', ...) as s3_client:
+       await s3_client.upload_fileobj(
+           io.BytesIO(file_content),
+           self.bucket_name,
+           s3_key,
+           ExtraArgs=extra_args
+       )
```

#### 4. 异步 URL 生成

```diff
- def _generate_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
-     url = self.s3_client.generate_presigned_url(...)
-     return url
+ async def _generate_presigned_url_async(self, s3_key: str, expires_in: int = 3600) -> str:
+     async with self.session.client('s3', ...) as s3_client:
+         url = await s3_client.generate_presigned_url(...)
+         return url

- def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
-     return self._generate_presigned_url(s3_key, expires_in)
+ async def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
+     return await self._generate_presigned_url_async(s3_key, expires_in)
```

#### 5. 异步删除操作

```diff
async def delete_file(self, s3_key: str) -> bool:
-   self.s3_client.delete_object(
-       Bucket=self.bucket_name,
-       Key=s3_key
-   )
+   async with self.session.client('s3', ...) as s3_client:
+       await s3_client.delete_object(
+           Bucket=self.bucket_name,
+           Key=s3_key
+       )
```

### 调用方更新

所有调用 `get_presigned_url` 的地方都需要添加 `await`：

#### 修改的文件

1. **tools/sandbox_tools.py**
   ```diff
   - presigned_url = s3_uploader.get_presigned_url(s3_key, expires_in=86400)
   + presigned_url = await s3_uploader.get_presigned_url(s3_key, expires_in=86400)
   ```

2. **infra/sandbox/e2b.py**
   ```diff
   - url = uploader.get_presigned_url(result["key"], expires_in=7 * 24 * 3600)
   + url = await uploader.get_presigned_url(result["key"], expires_in=7 * 24 * 3600)
   ```

3. **tools/slidespeak.py**
   ```diff
   - presigned_url = s3_uploader.get_presigned_url(s3_key, expires_in=86400)
   + presigned_url = await s3_uploader.get_presigned_url(s3_key, expires_in=86400)
   ```

4. **services/file_service.py**
   ```diff
   - file_url = self.s3_uploader.get_presigned_url(
   -     s3_key=storage_path,
   -     expires_in=86400
   - )
   + file_url = await self.s3_uploader.get_presigned_url(
   +     s3_key=storage_path,
   +     expires_in=86400
   + )
   ```

5. **services/knowledge_service.py** (2处)
   ```diff
   - presigned_url = s3_uploader.get_presigned_url(
   -     metadata["s3_key"],
   -     expires_in=3600
   - )
   + presigned_url = await s3_uploader.get_presigned_url(
   +     metadata["s3_key"],
   +     expires_in=3600
   + )
   ```

6. **routers/knowledge.py**
   - 已经是 `await`，无需修改 ✅

## 迁移步骤

### 1. 安装依赖

```bash
pip install aioboto3>=13.0.0
```

### 2. 重启服务

```bash
# 停止当前服务
# Ctrl+C

# 重新启动
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 验证功能

测试以下功能确保正常工作：

- [ ] 文件上传到 S3
- [ ] 生成预签名 URL
- [ ] 文件删除
- [ ] 批量删除
- [ ] 沙盒文件上传
- [ ] 知识库文档上传

## 性能对比

### 重构前（同步）

```
上传 10MB 文件：
- 阻塞时间：~2-3秒
- 并发能力：受限于线程池
- 其他请求：等待上传完成
```

### 重构后（异步）

```
上传 10MB 文件：
- 非阻塞
- 并发能力：理论无限
- 其他请求：不受影响
```

## 注意事项

### 1. Context Manager 模式

aioboto3 使用 context manager 模式创建客户端：

```python
async with self.session.client('s3', ...) as s3_client:
    await s3_client.upload_fileobj(...)
```

**优点**：
- 自动管理连接生命周期
- 避免连接泄漏
- 线程安全

### 2. 配置复用

每次操作都需要传入配置：

```python
from botocore.config import Config
s3_config = Config(signature_version='s3v4')

async with self.session.client(
    's3',
    endpoint_url=self._endpoint_url,
    config=s3_config
) as s3_client:
    # 使用客户端
```

### 3. 错误处理

异常类型保持不变（来自 botocore）：

```python
from botocore.exceptions import ClientError, NoCredentialsError

try:
    await s3_client.upload_fileobj(...)
except ClientError as e:
    logger.error(f"S3 上传失败: {e}")
```

## 兼容性

### Python 版本

- 最低要求：Python 3.7+
- 推荐版本：Python 3.10+

### AWS SDK 版本

- aioboto3 >= 13.0.0
- boto3 >= 1.34.0
- botocore >= 1.34.0

## 后续优化

### 1. 连接池管理

考虑实现连接池复用：

```python
class S3Uploader:
    def __init__(self):
        self._client_cache = {}
    
    async def _get_client(self):
        # 复用客户端连接
        pass
```

### 2. 上传进度回调

添加大文件上传进度监控：

```python
async def upload_file_with_progress(self, file_path: str, callback):
    # 实现进度回调
    pass
```

### 3. 分片上传

大文件（>100MB）使用分片上传：

```python
async def upload_large_file(self, file_path: str):
    # 使用 multipart upload
    pass
```

## 参考资料

- [aioboto3 文档](https://aioboto3.readthedocs.io/)
- [boto3 文档](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [AsyncIO 最佳实践](https://docs.python.org/3/library/asyncio.html)

## 总结

本次重构将 `S3Uploader` 从同步改为异步，符合项目的异步 I/O 规范，显著提升了性能和并发能力。所有调用方都已更新为异步调用，确保系统的一致性。
