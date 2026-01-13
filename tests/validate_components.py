"""
核心组件验证脚本
验证 ConflictResolver、DAG 生成、Workers 配置加载
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.multi_agent.scheduling.conflict_resolver import ConflictResolver
from core.multi_agent.decomposition.task_decomposer import TaskDecomposer
from core.multi_agent.fsm.states import SubTaskState, SubTaskStatus
from scripts.instance_loader import load_workers_config
from logger import get_logger

logger = get_logger("component_validator")


class ComponentValidator:
    """组件验证器"""
    
    def __init__(self):
        self.results = {
            "conflict_resolver": False,
            "dag_generation": False,
            "workers_config": False
        }
    
    def validate_conflict_resolver(self):
        """验证 ConflictResolver"""
        logger.info("=" * 80)
        logger.info("【组件 1】ConflictResolver 验证")
        logger.info("=" * 80)
        
        try:
            # 初始化
            resolver = ConflictResolver(default_lock_timeout=300)
            logger.info("✅ ConflictResolver 初始化成功")
            
            # 测试资源锁
            task_id = "test-task-1"
            resource = "src/test.py"
            
            # 获取锁
            acquired = resolver.acquire_lock(task_id, resource)
            logger.info(f"✅ 资源锁获取测试: {acquired}")
            
            # 检查锁状态
            is_locked = resolver.is_locked(resource)
            owner = resolver.get_lock_owner(resource)
            logger.info(f"✅ 锁状态检查: is_locked={is_locked}, owner={owner}")
            
            # 释放锁
            released = resolver.release_lock(resource)
            logger.info(f"✅ 资源锁释放测试: {released}")
            
            # 测试冲突检测
            sub_tasks = [
                SubTaskState(
                    id="task-1",
                    action="修改 src/auth.py 文件",
                    status=SubTaskStatus.PENDING,
                    dependencies=[],
                    specialization="refactor"
                ),
                SubTaskState(
                    id="task-2",
                    action="更新 src/auth.py 的测试",
                    status=SubTaskStatus.PENDING,
                    dependencies=[],
                    specialization="test"
                )
            ]
            
            conflicts = resolver.detect_conflicts(sub_tasks)
            logger.info(f"✅ 冲突检测测试: 检测到 {len(conflicts)} 个冲突")
            
            if conflicts:
                # 应用解决策略
                dependencies = resolver.resolve_conflicts(conflicts)
                logger.info(f"✅ 冲突解决测试: 生成 {sum(len(deps) for deps in dependencies.values())} 个依赖关系")
            
            self.results["conflict_resolver"] = True
            logger.info("✅ ConflictResolver 验证通过\n")
            
        except Exception as e:
            logger.error(f"❌ ConflictResolver 验证失败: {e}")
            self.results["conflict_resolver"] = False
    
    def validate_dag_generation(self):
        """验证 DAG 生成"""
        logger.info("=" * 80)
        logger.info("【组件 2】Mermaid DAG 生成验证")
        logger.info("=" * 80)
        
        try:
            # 直接测试 DAG 生成函数
            from core.multi_agent.decomposition.task_decomposer import TaskDecomposer
            
            # 创建测试子任务
            sub_tasks = [
                SubTaskState(
                    id="task-1",
                    action="研究 AWS 的 AI 战略",
                    status=SubTaskStatus.PENDING,
                    dependencies=[],
                    specialization="research"
                ),
                SubTaskState(
                    id="task-2",
                    action="研究 Azure 的 AI 战略",
                    status=SubTaskStatus.PENDING,
                    dependencies=[],
                    specialization="research"
                ),
                SubTaskState(
                    id="task-3",
                    action="对比分析 AWS 和 Azure",
                    status=SubTaskStatus.PENDING,
                    dependencies=["task-1", "task-2"],
                    specialization="analysis"
                )
            ]
            
            # 创建临时实例并生成 DAG
            decomposer = TaskDecomposer(llm_service=None, model="test")
            
            # 检查方法是否存在
            if not hasattr(decomposer, 'generate_mermaid_dag'):
                logger.warning("⚠️ generate_mermaid_dag 方法不存在，跳过验证")
                self.results["dag_generation"] = False
                return
            
            mermaid_dag = decomposer.generate_mermaid_dag(sub_tasks)
            
            logger.info("✅ Mermaid DAG 生成成功")
            logger.info(f"   DAG 长度: {len(mermaid_dag)} 字符")
            logger.info(f"   DAG 预览:\n{mermaid_dag[:300]}...")
            
            # 验证 DAG 格式
            assert "graph TD" in mermaid_dag, "DAG 应以 'graph TD' 开头"
            assert "task_1" in mermaid_dag or "task-1" in mermaid_dag, "DAG 应包含节点 ID"
            assert "-->" in mermaid_dag, "DAG 应包含依赖关系"
            
            logger.info("✅ Mermaid DAG 格式验证通过")
            
            self.results["dag_generation"] = True
            logger.info("✅ DAG 生成验证通过\n")
            
        except Exception as e:
            logger.error(f"❌ DAG 生成验证失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.results["dag_generation"] = False
    
    def validate_workers_config(self):
        """验证 Workers 配置加载"""
        logger.info("=" * 80)
        logger.info("【组件 3】Workers 配置加载验证")
        logger.info("=" * 80)
        
        try:
            # 加载 Workers 配置
            workers_config = load_workers_config("test_agent")
            
            if not workers_config:
                logger.warning("⚠️ Workers 配置为空，将使用默认配置")
                self.results["workers_config"] = False
                return
            
            logger.info(f"✅ Workers 配置加载成功: {len(workers_config)} 个 Worker")
            
            # 检查返回类型（可能是列表或字典）
            if isinstance(workers_config, list):
                # 列表格式
                for i, config in enumerate(workers_config):
                    worker_name = config.get('name', f'worker-{i}')
                    logger.info(f"   • {worker_name}:")
                    logger.info(f"     - specialization: {config.get('specialization')}")
                    logger.info(f"     - worker_type: {config.get('worker_type')}")
                    logger.info(f"     - enabled: {config.get('enabled')}")
                    logger.info(f"     - system_prompt 长度: {len(config.get('system_prompt', ''))} 字符")
                
                # 验证至少有 3 个 Worker
                assert len(workers_config) >= 3, "应至少有 3 个 Worker 配置"
                
                # 验证必须的 specialization
                specializations = [config.get('specialization') for config in workers_config]
                logger.info(f"   专业领域: {specializations}")
                
            elif isinstance(workers_config, dict):
                # 字典格式
                for worker_name, config in workers_config.items():
                    logger.info(f"   • {worker_name}:")
                    logger.info(f"     - specialization: {config.get('specialization')}")
                    logger.info(f"     - worker_type: {config.get('worker_type')}")
                    logger.info(f"     - enabled: {config.get('enabled')}")
                    logger.info(f"     - system_prompt 长度: {len(config.get('system_prompt', ''))} 字符")
                
                # 验证至少有 3 个 Worker
                assert len(workers_config) >= 3, "应至少有 3 个 Worker 配置"
                
                # 验证必须的 specialization
                specializations = [config.get('specialization') for config in workers_config.values()]
                logger.info(f"   专业领域: {specializations}")
            
            self.results["workers_config"] = True
            logger.info("✅ Workers 配置验证通过\n")
            
        except Exception as e:
            logger.error(f"❌ Workers 配置验证失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.results["workers_config"] = False
    
    def run_validation(self):
        """运行所有验证"""
        logger.info("\n")
        logger.info("=" * 80)
        logger.info("Multi-Agent 核心组件验证")
        logger.info("=" * 80)
        logger.info("\n")
        
        # 执行验证
        self.validate_conflict_resolver()
        self.validate_dag_generation()
        self.validate_workers_config()
        
        # 汇总结果
        logger.info("=" * 80)
        logger.info("验证结果汇总")
        logger.info("=" * 80)
        
        total = len(self.results)
        passed = sum(1 for v in self.results.values() if v)
        
        for component, result in self.results.items():
            status = "✅ 通过" if result else "❌ 失败"
            logger.info(f"{status} - {component}")
        
        logger.info("")
        logger.info(f"总计: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
        
        if passed == total:
            logger.info("🎉 所有组件验证通过！")
            return True
        else:
            logger.error(f"⚠️ 有 {total - passed} 个组件验证失败")
            return False


async def main():
    """主函数"""
    validator = ComponentValidator()
    success = validator.run_validation()
    
    # 返回状态码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
