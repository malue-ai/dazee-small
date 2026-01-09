# 🔧 E2B 沙盒使用规范

当使用 E2B 沙盒执行代码时：

## 基本原则
- 每次操作使用正确的 conversation_id
- 文件操作在 /home/user 目录下
- 安装依赖前检查是否已存在

## 文件操作
- 使用 sandbox_write_file 写入文件
- 使用 sandbox_read_file 读取文件
- 使用 sandbox_execute 执行命令

## 常见命令
```bash
# Python
pip install <package>
python script.py

# Node.js
npm install <package>
node script.js
```

## 注意事项
- 大文件操作可能需要时间
- 网络请求可能有限制
- 执行完成后清理临时文件

