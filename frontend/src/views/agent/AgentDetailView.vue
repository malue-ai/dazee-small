<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 -->
    <div class="h-16 flex items-center justify-between px-8 border-b border-gray-100 bg-white sticky top-0 z-10">
      <div class="flex items-center gap-4">
        <button 
          @click="$router.push('/agents')" 
          class="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900 transition-all"
        >
          <ArrowLeft class="w-5 h-5" />
        </button>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center font-bold text-lg text-gray-600 border border-gray-200">
            {{ agent?.name?.[0]?.toUpperCase() || 'A' }}
          </div>
          <div>
            <h1 class="text-base font-bold text-gray-800">{{ agent?.name || agentId }}</h1>
            <span class="text-xs text-gray-400 font-mono">{{ agentId }}</span>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button 
          @click="reloadAgent" 
          :disabled="reloading"
          class="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 text-gray-600 text-sm font-medium rounded-xl hover:bg-gray-50 hover:text-blue-600 transition-all shadow-sm disabled:opacity-50"
        >
          <RefreshCw class="w-4 h-4" :class="reloading ? 'animate-spin' : ''" />
          {{ reloading ? '重载中...' : '热重载' }}
        </button>
        <button 
          @click="saveChanges" 
          :disabled="saving || !hasChanges"
          class="flex items-center gap-2 px-5 py-2 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save class="w-4 h-4" />
          {{ saving ? '保存中...' : '保存更改' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-4">
        <Loader2 class="w-10 h-10 animate-spin text-gray-300" />
        <p class="text-sm text-gray-500">加载智能体配置...</p>
      </div>
    </div>

    <!-- 主内容区 -->
    <div v-else class="flex-1 flex overflow-hidden relative z-10">
      <!-- 左侧导航 -->
      <div class="w-60 border-r border-gray-100 bg-gray-50 p-4 flex flex-col gap-1">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          class="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all text-left"
          :class="activeTab === tab.id 
            ? 'bg-white shadow-sm text-gray-900 border border-gray-200' 
            : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-800'"
        >
          <component :is="tab.icon" class="w-4 h-4" :class="activeTab === tab.id ? 'text-gray-800' : 'text-gray-400'" />
          {{ tab.label }}
        </button>
      </div>

      <!-- 右侧内容 -->
      <div class="flex-1 overflow-hidden bg-white flex flex-col">
        <!-- Skills Tab (全高布局) -->
        <template v-if="activeTab === 'skills'">
          <div class="flex-1 flex overflow-hidden">
            <!-- 左侧：已安装 Skills 列表 -->
            <div class="w-[320px] border-r border-gray-100 bg-gray-50 flex flex-col">
              <div class="p-4 border-b border-gray-100 flex items-center justify-between bg-white">
                <h2 class="font-bold text-gray-800 text-sm">已安装 Skills</h2>
                <button 
                  @click="showInstallSkillModal = true"
                  class="p-1.5 text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
                  title="安装新 Skill"
                >
                  <Plus class="w-4 h-4" />
                </button>
              </div>
              
              <div class="flex-1 overflow-y-auto p-3 space-y-2">
                <div v-if="skillsLoading" class="flex justify-center py-8">
                  <Loader2 class="w-5 h-5 animate-spin text-gray-400" />
                </div>
                
                <div v-else-if="installedSkills.length === 0" class="text-center py-8 text-gray-400">
                  <Puzzle class="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p class="text-xs">暂无已安装的 Skills</p>
                </div>
                
                <div 
                  v-else
                  v-for="skill in installedSkills" 
                  :key="skill.name"
                  @click="selectSkill(skill)"
                  class="p-3 rounded-xl cursor-pointer border transition-all"
                  :class="selectedSkill?.name === skill.name 
                    ? 'bg-white shadow-md border-blue-500/20 ring-1 ring-blue-500/10' 
                    : 'bg-white border-gray-200 hover:border-blue-300 hover:shadow-sm'"
                >
                  <div class="flex items-center justify-between mb-1">
                    <span class="font-medium text-gray-800 text-sm truncate">{{ skill.name }}</span>
                    <div class="flex gap-1">
                      <span 
                        class="w-2 h-2 rounded-full"
                        :class="skill.is_enabled ? 'bg-green-500' : 'bg-gray-300'"
                        :title="skill.is_enabled ? '已启用' : '已禁用'"
                      ></span>
                    </div>
                  </div>
                  <p class="text-xs text-gray-500 line-clamp-2">{{ skill.description || '暂无描述' }}</p>
                </div>
              </div>
            </div>

            <!-- 右侧：详情与编辑 -->
            <div class="flex-1 flex flex-col bg-white overflow-hidden">
              <div v-if="!selectedSkill" class="flex-1 flex flex-col items-center justify-center text-gray-400">
                <div class="w-16 h-16 bg-gray-50 rounded-2xl flex items-center justify-center mb-3 border border-gray-100">
                  <Puzzle class="w-8 h-8 opacity-30" />
                </div>
                <p class="text-sm">选择一个 Skill 查看详情</p>
              </div>

              <template v-else>
                <!-- 头部操作栏 -->
                <div class="h-14 px-6 border-b border-gray-100 flex items-center justify-between flex-shrink-0 bg-white">
                  <div class="flex items-center gap-3">
                    <h2 class="font-bold text-gray-800">{{ selectedSkill.name }}</h2>
                    <span 
                      v-if="selectedSkill.is_registered"
                      class="px-2 py-0.5 text-[10px] font-medium bg-green-100 text-green-700 rounded-md"
                    >
                      已注册
                    </span>
                    <span 
                      v-else
                      class="px-2 py-0.5 text-[10px] font-medium bg-yellow-100 text-yellow-700 rounded-md"
                    >
                      待注册
                    </span>
                  </div>
                  
                  <div class="flex items-center gap-2">
                    <button 
                      v-if="!selectedSkill.is_registered"
                      @click="registerSkill(selectedSkill.name)"
                      :disabled="skillActionLoading"
                      class="px-3 py-1.5 text-xs font-medium text-green-600 bg-white border border-green-200 rounded-lg hover:bg-green-50 transition-colors flex items-center gap-1"
                    >
                      <CloudUpload class="w-3.5 h-3.5" /> 注册
                    </button>
                    
                    <button 
                      @click="toggleSkill(selectedSkill.name, !selectedSkill.is_enabled)"
                      :disabled="skillActionLoading"
                      class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1"
                      :class="selectedSkill.is_enabled 
                        ? 'text-gray-600 bg-white border border-gray-200 hover:bg-gray-50' 
                        : 'text-blue-600 bg-blue-50 border border-blue-200 hover:bg-blue-100'"
                    >
                      <Power class="w-3.5 h-3.5" />
                      {{ selectedSkill.is_enabled ? '禁用' : '启用' }}
                    </button>

                    <button 
                      @click="isEditingContent = !isEditingContent"
                      class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1"
                      :class="isEditingContent 
                        ? 'bg-blue-600 text-white shadow-sm' 
                        : 'text-gray-600 bg-white border border-gray-200 hover:bg-gray-50'"
                    >
                      <Edit3 class="w-3.5 h-3.5" />
                      {{ isEditingContent ? '完成编辑' : '编辑内容' }}
                    </button>

                    <button 
                      @click="uninstallSkill(selectedSkill.name)"
                      :disabled="skillActionLoading"
                      class="px-3 py-1.5 text-xs font-medium text-red-600 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors flex items-center gap-1"
                    >
                      <Trash2 class="w-3.5 h-3.5" /> 卸载
                    </button>
                  </div>
                </div>

                <!-- 内容区 -->
                <div class="flex-1 overflow-y-auto p-6 scrollbar-thin">
                  <!-- 加载详情中 -->
                  <div v-if="detailLoading" class="flex justify-center py-12">
                    <Loader2 class="w-8 h-8 animate-spin text-gray-300" />
                  </div>

                  <template v-else-if="skillDetail">
                    <!-- 编辑模式 -->
                    <div v-if="isEditingContent" class="h-full flex flex-col gap-4">
                      <div class="flex items-center justify-between">
                        <label class="text-sm font-bold text-gray-700">SKILL.md 内容</label>
                        <button 
                          @click="saveSkillContent"
                          :disabled="skillActionLoading"
                          class="px-3 py-1.5 text-xs font-medium bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors flex items-center gap-1"
                        >
                          <Save class="w-3.5 h-3.5" /> 保存更改
                        </button>
                      </div>
                      <textarea 
                        v-model="skillDetail.content"
                        class="flex-1 w-full p-4 bg-gray-50 border border-gray-200 rounded-xl font-mono text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                        spellcheck="false"
                      ></textarea>
                    </div>

                    <!-- 查看模式 -->
                    <div v-else class="space-y-6">
                      <!-- 基本信息卡片 -->
                      <div class="bg-gray-50/50 rounded-xl border border-gray-100 p-5">
                        <div class="grid grid-cols-2 gap-6 mb-4">
                          <div>
                            <label class="text-xs font-semibold text-gray-500 mb-1 block uppercase">ID</label>
                            <code class="text-xs bg-white px-2 py-1 rounded border border-gray-200 text-gray-600">{{ selectedSkill.skill_id || '未分配' }}</code>
                          </div>
                          <div>
                            <label class="text-xs font-semibold text-gray-500 mb-1 block uppercase">优先级</label>
                            <span class="text-xs font-medium text-gray-700">{{ skillDetail.priority }}</span>
                          </div>
                        </div>
                        <div>
                          <label class="text-xs font-semibold text-gray-500 mb-1 block uppercase">描述</label>
                          <p class="text-sm text-gray-700 leading-relaxed">{{ skillDetail.description || '暂无描述' }}</p>
                        </div>
                        <div v-if="skillDetail.preferred_for?.length" class="mt-4">
                          <label class="text-xs font-semibold text-gray-500 mb-2 block uppercase">适用场景</label>
                          <div class="flex flex-wrap gap-2">
                            <span 
                              v-for="tag in skillDetail.preferred_for" 
                              :key="tag"
                              class="px-2 py-1 bg-white border border-gray-200 rounded text-xs text-gray-600"
                            >
                              {{ tag }}
                            </span>
                          </div>
                        </div>
                      </div>

                      <!-- 文件结构 -->
                      <div class="grid grid-cols-2 gap-4">
                        <div class="p-4 rounded-xl border border-gray-100 bg-white">
                          <h3 class="text-xs font-bold text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <FileCode class="w-3.5 h-3.5" /> 脚本 (scripts/)
                          </h3>
                          <div class="space-y-1">
                            <div v-for="s in skillDetail.scripts" :key="s" class="text-xs font-mono text-gray-600 bg-gray-50 px-2 py-1.5 rounded">{{ s }}</div>
                            <div v-if="!skillDetail.scripts?.length" class="text-xs text-gray-400 italic">无脚本</div>
                          </div>
                        </div>
                        <div class="p-4 rounded-xl border border-gray-100 bg-white">
                          <h3 class="text-xs font-bold text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <FolderOpen class="w-3.5 h-3.5" /> 资源 (resources/)
                          </h3>
                          <div class="space-y-1">
                            <div v-for="r in skillDetail.resources" :key="r" class="text-xs font-mono text-gray-600 bg-gray-50 px-2 py-1.5 rounded">{{ r }}</div>
                            <div v-if="!skillDetail.resources?.length" class="text-xs text-gray-400 italic">无资源</div>
                          </div>
                        </div>
                      </div>

                      <!-- 文档内容 -->
                      <div class="rounded-xl border border-gray-200 overflow-hidden">
                        <div class="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                          <h3 class="text-xs font-bold text-gray-600 uppercase">SKILL.md</h3>
                        </div>
                        <div class="p-4 bg-white max-h-[400px] overflow-y-auto">
                          <pre class="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">{{ skillDetail.content }}</pre>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </template>
            </div>
          </div>
        </template>

        <!-- 其他 Tab 内容 (需添加滚动容器) -->
        <div v-else class="flex-1 overflow-y-auto p-8 scrollbar-thin">
          <!-- 基础信息 -->
          <div v-if="activeTab === 'basic'" class="max-w-3xl space-y-8">
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2 border-b border-gray-100 pb-4">
                <ClipboardList class="w-5 h-5 text-gray-500" />
                基础信息
              </h2>
              
              <div class="grid grid-cols-2 gap-6">
                <div class="flex flex-col gap-2">
                  <label class="text-sm font-medium text-gray-700">Agent ID</label>
                  <input 
                    :value="agentId" 
                    disabled
                    class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500 cursor-not-allowed font-mono"
                  >
                </div>
                
                <div class="flex flex-col gap-2">
                  <label class="text-sm font-medium text-gray-700">版本</label>
                  <input 
                    v-model="form.version" 
                    type="text"
                    class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all font-mono"
                  >
                </div>
              </div>

              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium text-gray-700">名称</label>
                <input 
                  v-model="form.name" 
                  type="text"
                  placeholder="智能体名称"
                  class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all"
                >
              </div>

              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium text-gray-700">描述</label>
                <textarea 
                  v-model="form.description" 
                  rows="3"
                  placeholder="描述智能体的功能和用途"
                  class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all"
                ></textarea>
              </div>

              <div class="flex items-center gap-4 pt-2">
                <label class="text-sm font-medium text-gray-700">状态</label>
                <label class="flex items-center gap-2 cursor-pointer select-none">
                  <div class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" v-model="form.is_active" class="sr-only peer">
                    <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-100 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-green-500"></div>
                  </div>
                  <span class="text-sm font-medium" :class="form.is_active ? 'text-green-600' : 'text-gray-500'">
                    {{ form.is_active ? '已激活' : '未激活' }}
                  </span>
                </label>
              </div>
            </div>
          </div>

          <!-- Prompt 配置 -->
          <div v-if="activeTab === 'prompt'" class="max-w-4xl space-y-6">
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2 border-b border-gray-100 pb-4">
                <PenTool class="w-5 h-5 text-gray-500" />
                系统提示词
              </h2>
              
              <div class="flex flex-col gap-2">
                <div class="flex items-center justify-between mb-1">
                  <label class="text-sm font-medium text-gray-700">System Prompt</label>
                  <span class="text-xs text-gray-400 font-mono">{{ form.prompt?.length || 0 }} 字符</span>
                </div>
                <textarea 
                  v-model="form.prompt" 
                  rows="20"
                  placeholder="设定智能体的角色、能力和行为准则..."
                  class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all font-mono leading-relaxed"
                ></textarea>
              </div>
            </div>
          </div>

          <!-- 模型配置 -->
          <div v-if="activeTab === 'model'" class="max-w-3xl space-y-6">
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2 border-b border-gray-100 pb-4">
                <BrainCircuit class="w-5 h-5 text-gray-500" />
                模型配置
              </h2>
              
              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium text-gray-700">模型选择</label>
                <div class="relative">
                  <select 
                    v-model="form.model"
                    class="w-full pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all cursor-pointer appearance-none"
                  >
                    <option value="claude-sonnet-4-20250514">Claude Sonnet 4 (最新)</option>
                    <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                    <option value="gpt-4o">GPT-4o</option>
                    <option value="gpt-4o-mini">GPT-4o Mini</option>
                    <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                  </select>
                  <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              </div>

              <div class="flex flex-col gap-2">
                <label class="text-sm font-medium text-gray-700">最大对话轮数</label>
                <input 
                  v-model.number="form.max_turns" 
                  type="number" 
                  min="1" 
                  max="100"
                  class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all"
                >
                <span class="text-xs text-gray-400">限制单次对话的最大工具调用轮数</span>
              </div>

              <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
                <input 
                  type="checkbox" 
                  v-model="form.plan_manager_enabled"
                  class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                >
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">启用计划管理器</div>
                  <div class="text-xs text-gray-500 mt-1">适合处理复杂的长流程任务</div>
                </div>
              </label>
            </div>
          </div>

          <!-- 工具配置 -->
          <div v-if="activeTab === 'tools'" class="max-w-4xl space-y-8">
            <!-- 内置工具 -->
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2 border-b border-gray-100 pb-4">
                <Zap class="w-5 h-5 text-gray-500" />
                内置工具
              </h2>
              
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <label 
                  v-for="cap in availableCapabilities" 
                  :key="cap.id"
                  class="flex items-start gap-3 p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all group"
                  :class="form.enabled_capabilities?.[cap.id] ? 'border-blue-200 bg-blue-50/10' : ''"
                >
                  <input 
                    type="checkbox" 
                    :checked="form.enabled_capabilities?.[cap.id]"
                    @change="toggleCapability(cap.id)"
                    class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  >
                  <div class="flex-1">
                    <div class="text-sm font-medium text-gray-700 flex items-center gap-2 mb-1">
                      <component :is="cap.icon" class="w-4 h-4 text-gray-500" />
                      {{ cap.label }}
                    </div>
                    <div class="text-xs text-gray-400 leading-snug">{{ cap.description }}</div>
                  </div>
                </label>
              </div>
            </div>

            <!-- MCP 工具 -->
            <div class="space-y-6">
              <div class="flex items-center justify-between border-b border-gray-100 pb-4">
                <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
                  <Plug class="w-5 h-5 text-gray-500" />
                  MCP 工具
                </h2>
                <button 
                  @click="fetchAvailableMcps"
                  class="text-sm text-gray-500 hover:text-gray-800 font-medium flex items-center gap-1"
                >
                  <RefreshCw class="w-3.5 h-3.5" />
                  刷新列表
                </button>
              </div>

              <!-- 已启用的 MCP -->
              <div v-if="enabledMcps.length > 0" class="space-y-3">
                <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">已启用 ({{ enabledMcps.length }})</h3>
                <div 
                  v-for="mcp in enabledMcps" 
                  :key="mcp.server_name"
                  class="flex items-center justify-between p-4 bg-green-50/50 border border-green-100 rounded-xl"
                >
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center text-green-600">
                      <Check class="w-5 h-5" />
                    </div>
                    <div>
                      <div class="font-medium text-gray-800 text-sm">{{ mcp.name || mcp.server_name }}</div>
                      <div class="text-xs text-gray-500">{{ mcp.description || '暂无描述' }}</div>
                      <div class="text-xs text-gray-400 mt-0.5 font-mono">{{ mcp.server_url }}</div>
                    </div>
                  </div>
                  <button 
                    @click="disableMcp(mcp.server_name || mcp.name)"
                    class="px-3 py-1.5 text-xs font-medium text-red-600 bg-white border border-red-100 rounded-lg hover:bg-red-50 transition-colors"
                  >
                    禁用
                  </button>
                </div>
              </div>

              <!-- 可用的 MCP -->
              <div v-if="availableMcps.length > 0" class="space-y-3">
                <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">可添加 ({{ availableMcps.length }})</h3>
                <div 
                  v-for="mcp in availableMcps" 
                  :key="mcp.server_name"
                  class="flex items-center justify-between p-4 bg-white border border-gray-200 rounded-xl hover:border-gray-300 transition-colors"
                >
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center text-gray-400">
                      <Plug class="w-5 h-5" />
                    </div>
                    <div>
                      <div class="font-medium text-gray-800 text-sm">{{ mcp.server_name }}</div>
                      <div class="text-xs text-gray-500">{{ mcp.description || '暂无描述' }}</div>
                    </div>
                  </div>
                  <button 
                    @click="enableMcp(mcp.server_name)"
                    class="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-100 rounded-lg hover:bg-blue-100 transition-colors"
                  >
                    启用
                  </button>
                </div>
              </div>

              <div v-if="enabledMcps.length === 0 && availableMcps.length === 0" class="text-center py-8 bg-gray-50 rounded-xl border border-gray-100 border-dashed">
                <Plug class="w-8 h-8 text-gray-300 mx-auto mb-2" />
                <p class="text-sm text-gray-500">暂无可用的 MCP 工具</p>
                <p class="text-xs text-gray-400 mt-1">在 config.yaml 的 mcp_tools 中配置</p>
              </div>
            </div>

            <!-- REST APIs -->
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2 border-b border-gray-100 pb-4">
                <Globe class="w-5 h-5 text-gray-500" />
                REST APIs
              </h2>

              <div v-if="agent?.apis?.length > 0" class="space-y-3">
                <div 
                  v-for="api in agent.apis" 
                  :key="api.name"
                  class="flex items-center justify-between p-4 bg-blue-50/30 border border-blue-100 rounded-xl"
                >
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center text-blue-600">
                      <Globe class="w-5 h-5" />
                    </div>
                    <div>
                      <div class="font-medium text-gray-800 text-sm">{{ api.name }}</div>
                      <div class="text-xs text-gray-500">{{ api.description || '暂无描述' }}</div>
                      <div class="text-xs text-gray-400 mt-0.5 font-mono">{{ api.base_url }}</div>
                    </div>
                  </div>
                  <span class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded-md font-medium">{{ api.auth_type || 'none' }}</span>
                </div>
              </div>

              <div v-else class="text-center py-8 bg-gray-50 rounded-xl border border-gray-100 border-dashed">
                <Globe class="w-8 h-8 text-gray-300 mx-auto mb-2" />
                <p class="text-sm text-gray-500">暂无 REST API 配置</p>
                <p class="text-xs text-gray-400 mt-1">在 config.yaml 的 apis 中配置</p>
              </div>
            </div>
          </div>

          <!-- 危险操作 -->
          <div v-if="activeTab === 'danger'" class="max-w-3xl space-y-6">
            <div class="space-y-6">
              <h2 class="text-lg font-bold text-red-600 flex items-center gap-2 border-b border-red-100 pb-4">
                <AlertTriangle class="w-5 h-5" />
                危险操作
              </h2>
              
              <div class="p-6 bg-red-50/50 rounded-xl border border-red-100">
                <h3 class="font-semibold text-gray-800 mb-2 text-sm">删除智能体</h3>
                <p class="text-sm text-gray-500 mb-4 leading-relaxed">此操作将永久删除该智能体的所有配置文件，无法恢复。请谨慎操作。</p>
                <button 
                  @click="deleteAgent"
                  :disabled="deleting"
                  class="px-5 py-2.5 bg-white border border-red-200 text-red-600 text-sm font-medium rounded-lg hover:bg-red-50 transition-all disabled:opacity-50"
                >
                  {{ deleting ? '删除中...' : '删除智能体' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 安装 Skill Modal -->
    <Teleport to="body">
      <div 
        v-if="showInstallSkillModal"
        class="fixed inset-0 bg-gray-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        @click.self="showInstallSkillModal = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden max-h-[80vh] flex flex-col">
          <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
            <h3 class="text-lg font-bold text-gray-900">从全局库安装 Skill</h3>
            <button @click="showInstallSkillModal = false" class="p-2 rounded-lg text-gray-400 hover:bg-gray-100">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="p-6 overflow-y-auto flex-1">
            <!-- 加载中 -->
            <div v-if="globalSkillsLoading" class="flex items-center justify-center py-8 text-gray-400">
              <Loader2 class="w-6 h-6 animate-spin mr-2" /> 加载全局库...
            </div>
            <!-- 空状态 -->
            <div v-else-if="availableGlobalSkills.length === 0" class="text-center py-8 text-gray-400">
              <Puzzle class="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p class="text-sm">全局库为空或所有 Skills 已安装</p>
            </div>
            <!-- Skills 列表 -->
            <div v-else class="space-y-3">
              <div 
                v-for="skill in availableGlobalSkills" 
                :key="skill.name"
                class="flex items-center justify-between p-4 bg-gray-50 border border-gray-200 rounded-xl hover:border-blue-300 transition-colors"
              >
                <div class="flex-1">
                  <div class="font-medium text-gray-800 text-sm">{{ skill.name }}</div>
                  <div class="text-xs text-gray-500 mt-1 line-clamp-2">{{ skill.description || '暂无描述' }}</div>
                </div>
                <button 
                  @click="installSkill(skill.name)"
                  :disabled="skillActionLoading"
                  class="ml-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  安装
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api/index'
import * as skillsApi from '@/api/skills'
import { 
  ArrowLeft, 
  RefreshCw, 
  Save, 
  Loader2, 
  ClipboardList, 
  PenTool, 
  BrainCircuit, 
  Wrench, 
  AlertTriangle, 
  Zap, 
  Plug, 
  Globe,
  ChevronDown,
  Check,
  Puzzle,
  Power,
  Trash2,
  Download,
  CloudUpload,
  Plus,
  FileCode,
  FolderOpen,
  Edit3
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()

// 从路由获取 agent_id
const agentId = computed(() => route.params.agentId)

// 状态
const loading = ref(true)
const saving = ref(false)
const reloading = ref(false)
const deleting = ref(false)
const agent = ref(null)
const activeTab = ref('basic')

// 原始数据（用于检测变更）
const originalData = ref(null)

// 表单数据
const form = reactive({
  name: '',
  description: '',
  version: '1.0.0',
  is_active: true,
  prompt: '',
  model: 'claude-3-5-sonnet-20241022',
  max_turns: 20,
  plan_manager_enabled: false,
  enabled_capabilities: {
    tavily_search: false,
    knowledge_search: false,
    code_execution: false,
    sandbox_tools: false,
  }
})

// MCP 数据
const enabledMcps = ref([])
const availableMcps = ref([])

// Skills 数据
const installedSkills = ref([])
const globalSkills = ref([])
const selectedSkill = ref(null)
const skillDetail = ref(null)
const skillsLoading = ref(false)
const globalSkillsLoading = ref(false)
const skillActionLoading = ref(false)
const detailLoading = ref(false)
const showInstallSkillModal = ref(false)
const isEditingContent = ref(false)

// 标签页配置
const tabs = [
  { id: 'basic', label: '基础信息', icon: ClipboardList },
  { id: 'prompt', label: '提示词', icon: PenTool },
  { id: 'model', label: '模型配置', icon: BrainCircuit },
  { id: 'tools', label: '工具配置', icon: Wrench },
  { id: 'skills', label: 'Skills', icon: Puzzle },
  { id: 'danger', label: '危险操作', icon: AlertTriangle },
]

// 可用能力列表（与后端 enabled_capabilities 配置一致）
const availableCapabilities = [
  { id: 'tavily_search', label: '网络搜索', icon: Globe, description: '允许搜索互联网获取信息（Tavily API）' },
  { id: 'knowledge_search', label: '知识库检索', icon: ClipboardList, description: '从用户知识库中检索相关内容' },
  { id: 'code_execution', label: '代码执行', icon: Zap, description: '动态执行代码' },
  { id: 'sandbox_tools', label: '沙盒工具', icon: ClipboardList, description: '文件操作、命令执行等沙盒能力' },
]

// 可安装的全局 Skills（排除已安装的）
const availableGlobalSkills = computed(() => {
  const installedNames = new Set(installedSkills.value.map(s => s.name))
  return globalSkills.value.filter(s => !installedNames.has(s.name))
})

// 检测是否有变更
const hasChanges = computed(() => {
  if (!originalData.value) return false
  return JSON.stringify(form) !== JSON.stringify(originalData.value)
})

// 加载 Agent 详情
const fetchAgent = async () => {
  try {
    loading.value = true
    
    // 并行获取详情和 prompt
    const [detailResponse, promptResponse] = await Promise.all([
      api.get(`/v1/agents/${agentId.value}`),
      api.get(`/v1/agents/${agentId.value}/prompt`).catch(() => ({ data: { prompt: '' } }))
    ])
    
    agent.value = detailResponse.data
    
    // 填充表单
    form.name = detailResponse.data.name || agentId.value
    form.description = detailResponse.data.description || ''
    form.version = detailResponse.data.version || '1.0.0'
    form.is_active = detailResponse.data.is_active ?? true
    form.model = detailResponse.data.model || 'claude-3-5-sonnet-20241022'
    form.max_turns = detailResponse.data.max_turns || 20
    form.plan_manager_enabled = detailResponse.data.plan_manager_enabled || false
    
    // 处理 enabled_capabilities（与后端配置一致）
    if (detailResponse.data.enabled_capabilities && typeof detailResponse.data.enabled_capabilities === 'object') {
      form.enabled_capabilities = {
        tavily_search: !!detailResponse.data.enabled_capabilities.tavily_search,
        knowledge_search: !!detailResponse.data.enabled_capabilities.knowledge_search,
        code_execution: !!detailResponse.data.enabled_capabilities.code_execution,
        sandbox_tools: !!detailResponse.data.enabled_capabilities.sandbox_tools,
      }
    }
    
    // 加载 Prompt
    form.prompt = promptResponse.data.prompt || ''
    
    // 保存原始数据
    originalData.value = JSON.parse(JSON.stringify(form))
    
  } catch (error) {
    console.error('获取 Agent 详情失败:', error)
    alert('获取 Agent 详情失败')
    router.push('/agents')
  } finally {
    loading.value = false
  }
}

// 加载 MCP 列表
const fetchMcps = async () => {
  try {
    enabledMcps.value = agent.value?.mcp_tools || []
    
    const availableResponse = await api.get(`/v1/agents/${agentId.value}/mcp/available`)
    const enabledNames = new Set(enabledMcps.value.map(m => m.name || m.server_name))
    availableMcps.value = (availableResponse.data.mcps || []).filter(
      mcp => !enabledNames.has(mcp.server_name) && !mcp.is_enabled_by_agent
    )
  } catch (error) {
    console.error('获取 MCP 列表失败:', error)
    enabledMcps.value = agent.value?.mcp_tools || []
  }
}

const fetchAvailableMcps = fetchMcps

// 加载已安装的 Skills
const fetchInstalledSkills = async () => {
  skillsLoading.value = true
  try {
    installedSkills.value = await skillsApi.getInstanceSkills(agentId.value)
    // 如果之前选中了 Skill，刷新后尝试保持选中
    if (selectedSkill.value) {
      const found = installedSkills.value.find(s => s.name === selectedSkill.value.name)
      if (found) {
        // 更新选中状态但不重置详情（如果已经在详情页）
        selectedSkill.value = found
      } else {
        selectedSkill.value = null
        skillDetail.value = null
      }
    }
  } catch (error) {
    console.error('获取已安装 Skills 失败:', error)
    installedSkills.value = []
  } finally {
    skillsLoading.value = false
  }
}

// 加载全局 Skills
const fetchGlobalSkills = async () => {
  globalSkillsLoading.value = true
  try {
    globalSkills.value = await skillsApi.getGlobalSkills()
  } catch (error) {
    console.error('获取全局 Skills 失败:', error)
    globalSkills.value = []
  } finally {
    globalSkillsLoading.value = false
  }
}

// 选择 Skill 查看详情
const selectSkill = async (skill) => {
  selectedSkill.value = skill
  skillDetail.value = null
  isEditingContent.value = false
  
  detailLoading.value = true
  try {
    skillDetail.value = await skillsApi.getSkillDetail(skill.name, agentId.value)
  } catch (error) {
    console.error('获取 Skill 详情失败:', error)
  } finally {
    detailLoading.value = false
  }
}

// 安装 Skill
const installSkill = async (skillName) => {
  skillActionLoading.value = true
  try {
    const result = await skillsApi.installSkill({
      skill_name: skillName,
      agent_id: agentId.value,
      auto_register: true
    })
    alert(result.message)
    showInstallSkillModal.value = false
    await fetchInstalledSkills()
  } catch (error) {
    console.error('安装 Skill 失败:', error)
    alert('安装失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    skillActionLoading.value = false
  }
}

// 卸载 Skill
const uninstallSkill = async (skillName) => {
  if (!confirm(`确定要卸载 "${skillName}" 吗？`)) return
  
  skillActionLoading.value = true
  try {
    const result = await skillsApi.uninstallSkill({
      skill_name: skillName,
      agent_id: agentId.value
    })
    alert(result.message)
    if (selectedSkill.value?.name === skillName) {
      selectedSkill.value = null
      skillDetail.value = null
    }
    await fetchInstalledSkills()
  } catch (error) {
    console.error('卸载 Skill 失败:', error)
    alert('卸载失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    skillActionLoading.value = false
  }
}

// 启用/禁用 Skill
const toggleSkill = async (skillName, enabled) => {
  skillActionLoading.value = true
  try {
    const result = await skillsApi.toggleSkill({
      skill_name: skillName,
      agent_id: agentId.value,
      enabled
    })
    alert(result.message)
    await fetchInstalledSkills()
  } catch (error) {
    console.error('切换 Skill 状态失败:', error)
    alert('操作失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    skillActionLoading.value = false
  }
}

// 注册 Skill 到 Claude API
const registerSkill = async (skillName) => {
  skillActionLoading.value = true
  try {
    const result = await skillsApi.registerSkill(skillName, agentId.value)
    alert(result.message)
    await fetchInstalledSkills()
  } catch (error) {
    console.error('注册 Skill 失败:', error)
    alert('注册失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    skillActionLoading.value = false
  }
}

// 保存 Skill 内容
const saveSkillContent = async () => {
  if (!selectedSkill.value || !skillDetail.value) return
  
  skillActionLoading.value = true
  try {
    const result = await skillsApi.updateSkillContent({
      skill_name: selectedSkill.value.name,
      agent_id: agentId.value,
      content: skillDetail.value.content
    })
    
    alert(result.message)
    isEditingContent.value = false
    // 重新获取详情以确保同步
    await selectSkill(selectedSkill.value)
  } catch (error) {
    console.error('保存 Skill 内容失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    skillActionLoading.value = false
  }
}

// 保存 Agent 更改
const saveChanges = async () => {
  try {
    saving.value = true
    
    const updateData = {
      description: form.description,
      model: form.model,
      max_turns: form.max_turns,
      plan_manager_enabled: form.plan_manager_enabled,
      enabled_capabilities: form.enabled_capabilities,
      is_active: form.is_active,
    }
    
    if (form.prompt !== originalData.value?.prompt) {
      updateData.prompt = form.prompt
    }
    
    await api.put(`/v1/agents/${agentId.value}`, updateData)
    
    originalData.value = JSON.parse(JSON.stringify(form))
    
    alert('保存成功！')
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    saving.value = false
  }
}

// 热重载
const reloadAgent = async () => {
  try {
    reloading.value = true
    await api.post(`/v1/agents/${agentId.value}/reload`)
    await fetchAgent()
    alert('热重载成功！')
  } catch (error) {
    console.error('热重载失败:', error)
    alert('热重载失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    reloading.value = false
  }
}

// 删除 Agent
const deleteAgent = async () => {
  if (!confirm(`确定要删除智能体 "${agentId.value}" 吗？此操作无法恢复！`)) return
  
  try {
    deleting.value = true
    await api.delete(`/v1/agents/${agentId.value}`)
    alert('删除成功！')
    router.push('/agents')
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    deleting.value = false
  }
}

// 切换能力
const toggleCapability = (capId) => {
  form.enabled_capabilities[capId] = !form.enabled_capabilities[capId]
}

// 启用 MCP
const enableMcp = async (serverName) => {
  try {
    await api.post(`/v1/agents/${agentId.value}/mcp/${serverName}`, {})
    await fetchMcps()
  } catch (error) {
    console.error('启用 MCP 失败:', error)
    alert('启用 MCP 失败: ' + (error.response?.data?.detail?.message || error.message))
  }
}

// 禁用 MCP
const disableMcp = async (serverName) => {
  if (!confirm(`确定要禁用 MCP "${serverName}" 吗？`)) return
  
  try {
    await api.delete(`/v1/agents/${agentId.value}/mcp/${serverName}`)
    await fetchMcps()
  } catch (error) {
    console.error('禁用 MCP 失败:', error)
    alert('禁用 MCP 失败: ' + (error.response?.data?.detail?.message || error.message))
  }
}

// 生命周期
onMounted(async () => {
  await fetchAgent()
  await fetchMcps()
  await fetchInstalledSkills()
  await fetchGlobalSkills()
})

// 监听路由变化
watch(() => route.params.agentId, async (newId) => {
  if (newId) {
    selectedSkill.value = null
    skillDetail.value = null
    isEditingContent.value = false
    await fetchAgent()
    await fetchMcps()
    await fetchInstalledSkills()
    await fetchGlobalSkills()
  }
})
</script>

<style scoped>
/* 滚动条优化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}

.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
