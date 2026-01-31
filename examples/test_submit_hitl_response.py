import sys
import os
import json
import asyncio
import grpc

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from grpc_server.generated import tool_service_pb2
    from grpc_server.generated import tool_service_pb2_grpc
except ImportError:
    print("❌ Failed to import generated gRPC modules. Please ensure grpc_server/generated exists.")
    sys.exit(1)

SESSION_ID = "750cb8eb-dac0-4e43-a3ec-8bcd5175251c"
GRPC_ADDRESS = "localhost:50051"

async def main():
    print(f"🚀 Connecting to gRPC server at {GRPC_ADDRESS}...")
    async with grpc.aio.insecure_channel(GRPC_ADDRESS) as channel:
        stub = tool_service_pb2_grpc.ConfirmationServiceStub(channel)

        # 1. Check pending requests
        print(f"\n🔍 Checking pending requests for session: {SESSION_ID}")
        try:
            response = await stub.GetPendingRequests(
                tool_service_pb2.GetPendingRequestsRequest(session_id=SESSION_ID)
            )
        except grpc.RpcError as e:
            print(f"❌ Failed to get pending requests: {e}")
            return

        target_request = None
        if response.requests:
            for req in response.requests:
                # Assuming request_id is session_id, or we match by session_id
                if req.session_id == SESSION_ID or req.request_id == SESSION_ID:
                    target_request = req
                    break
            
            # If not found by exact match, but list has items and we filtered by session_id, pick the first one
            if not target_request and len(response.requests) > 0:
                 target_request = response.requests[0]
        
        if not target_request:
            print("⚠️ No pending HITL request found for this session.")
            print("   (This might happen if the session expired or the request was already handled)")
            
            # Debug: List all requests if none found for session
            print("\n🔍 Debug: Listing ALL pending requests on server...")
            try:
                all_resp = await stub.GetPendingRequests(tool_service_pb2.GetPendingRequestsRequest())
                if not all_resp.requests:
                    print("   No pending requests on server.")
                for r in all_resp.requests:
                    print(f"   - Request ID: {r.request_id}, Session ID: {r.session_id}")
            except:
                pass
            return

        print(f"✅ Found pending request: {target_request.request_id}")
        print(f"   Question: {target_request.question}")
        # print(f"   Options: {target_request.options}")

        # 2. Construct Response
        # Based on the questions in the provided JSON
        form_response = {
            "game_type": "益智类（如2048、俄罗斯方块）",
            "complexity": "简单小游戏（单页面，快速完成）",
            "description": "暂无，希望您推荐"
        }
        response_str = json.dumps(form_response, ensure_ascii=False)
        
        print(f"\n📤 Submitting response...")
        print(f"   Response: {response_str}")

        # 3. Submit Response
        try:
            submit_resp = await stub.SubmitResponse(
                tool_service_pb2.SubmitConfirmationRequest(
                    request_id=target_request.request_id,
                    response=response_str
                )
            )
            
            if submit_resp.success:
                print("✅ Response submitted successfully!")
                print(f"   Response: {submit_resp.response}")
            else:
                print(f"❌ Submission failed: {submit_resp.error}")
                
        except grpc.RpcError as e:
            print(f"❌ gRPC call failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
