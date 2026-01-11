#!/bin/bash
# 生成 gRPC Python 代码
# 使用方法：bash scripts/generate_grpc.sh

set -e

echo "🔧 生成 gRPC Python 代码..."

# 确保在项目根目录
cd "$(dirname "$0")/.."

# 输出目录
OUTPUT_DIR="grpc_server/generated"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 生成 Python 代码
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./$OUTPUT_DIR \
    --grpc_python_out=./$OUTPUT_DIR \
    --pyi_out=./$OUTPUT_DIR \
    ./protos/tool_service.proto

# 创建 __init__.py
cat > "$OUTPUT_DIR/__init__.py" << 'EOF'
# gRPC 生成的代码
# 自动生成，请勿手动修改

from .tool_service_pb2 import *
from .tool_service_pb2_grpc import *
EOF

# 修复导入路径问题（grpc_tools 生成的代码使用绝对导入，需要改为相对导入）
echo "🔧 修复导入路径..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' 's/^import tool_service_pb2/from . import tool_service_pb2/' "$OUTPUT_DIR/tool_service_pb2_grpc.py"
else
    # Linux
    sed -i 's/^import tool_service_pb2/from . import tool_service_pb2/' "$OUTPUT_DIR/tool_service_pb2_grpc.py"
fi

echo "✅ gRPC 代码生成完成！"
echo "📁 输出目录: $OUTPUT_DIR/"
echo ""
echo "生成的文件："
ls -lh "$OUTPUT_DIR/"
