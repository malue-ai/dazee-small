#!/bin/bash
# 生成 gRPC Python 代码
# 使用方法：bash scripts/generate_grpc.sh

set -e

echo "🔧 生成 gRPC Python 代码..."

# 确保在项目根目录
cd "$(dirname "$0")/.."

# 创建输出目录
mkdir -p services/grpc/generated

# 生成 Python 代码
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./services/grpc/generated \
    --grpc_python_out=./services/grpc/generated \
    --pyi_out=./services/grpc/generated \
    ./protos/tool_service.proto

# 创建 __init__.py
touch services/grpc/__init__.py
touch services/grpc/generated/__init__.py

# 修复导入路径问题（grpc_tools 生成的代码使用绝对导入，需要改为相对导入）
echo "🔧 修复导入路径..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' 's/^import tool_service_pb2/from . import tool_service_pb2/' services/grpc/generated/tool_service_pb2_grpc.py
else
    # Linux
    sed -i 's/^import tool_service_pb2/from . import tool_service_pb2/' services/grpc/generated/tool_service_pb2_grpc.py
fi

echo "✅ gRPC 代码生成完成！"
echo "📁 输出目录: services/grpc/generated/"
echo ""
echo "生成的文件："
ls -lh services/grpc/generated/

