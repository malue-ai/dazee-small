#!/bin/bash
# 生成 gRPC Python 和 Go 代码
# 使用方法：bash scripts/generate_grpc.sh [--python-only | --go-only]

set -e

# 确保在项目根目录
cd "$(dirname "$0")/.."

# 解析参数
GENERATE_PYTHON=true
GENERATE_GO=true

if [[ "$1" == "--python-only" ]]; then
    GENERATE_GO=false
elif [[ "$1" == "--go-only" ]]; then
    GENERATE_PYTHON=false
fi

# ==================== Python 代码生成 ====================
if [[ "$GENERATE_PYTHON" == true ]]; then
    echo "🐍 生成 gRPC Python 代码..."
    
    # Python 输出目录
    PY_OUTPUT_DIR="grpc_server/generated"
    mkdir -p "$PY_OUTPUT_DIR"
    
    # 生成 Python 代码
    python -m grpc_tools.protoc \
        -I./protos \
        --python_out=./$PY_OUTPUT_DIR \
        --grpc_python_out=./$PY_OUTPUT_DIR \
        --pyi_out=./$PY_OUTPUT_DIR \
        ./protos/tool_service.proto
    
    # 创建 __init__.py
    cat > "$PY_OUTPUT_DIR/__init__.py" << 'EOF'
# gRPC 生成的代码
# 自动生成，请勿手动修改

from .tool_service_pb2 import *
from .tool_service_pb2_grpc import *
EOF
    
    # 修复导入路径问题（grpc_tools 生成的代码使用绝对导入，需要改为相对导入）
    echo "🔧 修复 Python 导入路径..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/^import tool_service_pb2/from . import tool_service_pb2/' "$PY_OUTPUT_DIR/tool_service_pb2_grpc.py"
    else
        sed -i 's/^import tool_service_pb2/from . import tool_service_pb2/' "$PY_OUTPUT_DIR/tool_service_pb2_grpc.py"
    fi
    
    echo "✅ Python gRPC 代码生成完成！"
    echo "📁 输出目录: $PY_OUTPUT_DIR/"
    ls -lh "$PY_OUTPUT_DIR/"
    echo ""
fi

# ==================== Go 代码生成 ====================
if [[ "$GENERATE_GO" == true ]]; then
    echo "🐹 生成 gRPC Go 客户端代码..."
    
    # Go 输出目录
    GO_OUTPUT_DIR="grpc_client_go"
    mkdir -p "$GO_OUTPUT_DIR"
    
    # 检查 protoc-gen-go 和 protoc-gen-go-grpc 是否安装
    if ! command -v protoc-gen-go &> /dev/null; then
        echo "❌ 错误: protoc-gen-go 未安装"
        echo "请运行以下命令安装："
        echo "  go install google.golang.org/protobuf/cmd/protoc-gen-go@latest"
        echo "  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest"
        echo ""
        echo "确保 \$GOPATH/bin 在 PATH 中："
        echo "  export PATH=\"\$PATH:\$(go env GOPATH)/bin\""
        exit 1
    fi
    
    if ! command -v protoc-gen-go-grpc &> /dev/null; then
        echo "❌ 错误: protoc-gen-go-grpc 未安装"
        echo "请运行: go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest"
        exit 1
    fi
    
    # 生成 Go 代码
    protoc \
        -I./protos \
        --go_out=./$GO_OUTPUT_DIR \
        --go_opt=paths=source_relative \
        --go-grpc_out=./$GO_OUTPUT_DIR \
        --go-grpc_opt=paths=source_relative \
        ./protos/tool_service.proto
    
    # 创建 go.mod（如果不存在）
    if [[ ! -f "$GO_OUTPUT_DIR/go.mod" ]]; then
        echo "📦 初始化 Go 模块..."
        cd "$GO_OUTPUT_DIR"
        go mod init github.com/zenflux/agent-client-go
        go mod tidy
        cd ..
    fi
    
    echo "✅ Go gRPC 代码生成完成！"
    echo "📁 输出目录: $GO_OUTPUT_DIR/"
    ls -lh "$GO_OUTPUT_DIR/"
    echo ""
fi

# ==================== 总结 ====================
echo "=========================================="
echo "📋 生成完成总结"
echo "=========================================="
if [[ "$GENERATE_PYTHON" == true ]]; then
    echo "🐍 Python 客户端: grpc_server/generated/"
fi
if [[ "$GENERATE_GO" == true ]]; then
    echo "🐹 Go 客户端:     grpc_client_go/"
    echo ""
    echo "📖 Go 客户端使用方法："
    echo "   1. 将 grpc_client_go/ 复制到你的 Go 项目"
    echo "   2. 或者在 go.mod 中使用 replace 指令引用本地路径"
    echo "   3. 示例代码见: examples/grpc_client_go_example.go"
fi
