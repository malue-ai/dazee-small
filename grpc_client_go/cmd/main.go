// gRPC 流式聊天接口测试客户端
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	// 命令行参数
	serverAddr := flag.String("addr", "localhost:50051", "gRPC 服务地址")
	message := flag.String("msg", "你好，请介绍一下你自己", "发送的消息")
	userId := flag.String("user", "test-user-go", "用户 ID")
	flag.Parse()

	log.Printf("连接到 gRPC 服务: %s", *serverAddr)

	// 建立连接
	conn, err := grpc.NewClient(*serverAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("连接失败: %v", err)
	}
	defer conn.Close()

	// 创建客户端
	client := NewChatServiceClient(conn)

	// 构建请求
	req := &ChatRequest{
		Message: *message,
		UserId:  *userId,
		Stream:  true,
	}

	log.Printf("发送消息: %s", *message)
	log.Printf("用户 ID: %s", *userId)
	log.Println("-------------------------------------------")

	// 调用流式接口
	// 🔧 增加超时时间到 30 分钟，避免长时间任务被提前取消
	// 对于 PPT 生成、视频处理等耗时任务，可能需要更长时间
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	stream, err := client.ChatStream(ctx, req)
	if err != nil {
		log.Fatalf("调用 ChatStream 失败: %v", err)
	}

	// 接收流式事件
	eventCount := 0
	startTime := time.Now()

	for {
		event, err := stream.Recv()
		if err == io.EOF {
			log.Println("-------------------------------------------")
			log.Printf("流式结束，共收到 %d 个事件，耗时: %v", eventCount, time.Since(startTime))
			break
		}
		if err != nil {
			log.Fatalf("接收事件失败: %v", err)
		}

		eventCount++
		printEvent(eventCount, event)
	}
}

// printEvent 格式化打印事件
func printEvent(seq int, event *ChatEvent) {
	fmt.Printf("\n[事件 #%d] 类型: %s\n", seq, event.EventType)
	fmt.Printf("  时间戳: %d\n", event.Timestamp)
	
	if event.Seq != nil {
		fmt.Printf("  序列号: %d\n", *event.Seq)
	}
	if event.EventUuid != nil {
		fmt.Printf("  UUID: %s\n", *event.EventUuid)
	}

	// 尝试格式化 JSON 数据
	if event.Data != "" {
		var jsonData map[string]interface{}
		if err := json.Unmarshal([]byte(event.Data), &jsonData); err == nil {
			prettyJSON, _ := json.MarshalIndent(jsonData, "  ", "  ")
			fmt.Printf("  数据:\n  %s\n", string(prettyJSON))
		} else {
			// 如果不是 JSON，直接打印
			if len(event.Data) > 200 {
				fmt.Printf("  数据: %s... (截断, 共 %d 字符)\n", event.Data[:200], len(event.Data))
			} else {
				fmt.Printf("  数据: %s\n", event.Data)
			}
		}
	}
}

