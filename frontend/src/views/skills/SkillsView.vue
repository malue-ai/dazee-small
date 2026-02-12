<template>
  <div class="h-full flex flex-col overflow-hidden bg-background">
    <!-- 顶部工具栏 -->
    <div class="h-14 flex items-center justify-between px-6 border-b border-border bg-background sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <!-- 返回聊天 -->
        <router-link
          to="/"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <ArrowLeft class="w-4 h-4" />
          <span>返回</span>
        </router-link>

        <div class="w-px h-5 bg-border"></div>

        <!-- Tab 切换 -->
        <div class="flex items-center gap-1 bg-muted rounded-lg p-1">
          <button
            @click="handleSwitchTab('library')"
            class="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
            :class="skillStore.activeTab === 'library'
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'"
          >
            <span class="flex items-center gap-1.5">
              <Puzzle class="w-3.5 h-3.5" />
              技能库
            </span>
          </button>
          <button
            @click="handleSwitchTab('project')"
            class="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
            :class="skillStore.activeTab === 'project'
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'"
          >
            <span class="flex items-center gap-1.5">
              <Bot class="w-3.5 h-3.5" />
              项目技能
            </span>
          </button>
        </div>

        <!-- 数量标识 -->
        <div class="text-xs text-muted-foreground bg-muted px-2 py-1 rounded-md border border-border">
          {{ skillStore.currentSkills.length }} 个
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- 项目技能 tab：Agent 选择器（自定义下拉） -->
        <div v-if="skillStore.activeTab === 'project'" class="relative" ref="agentDropdownRef">
          <button
            @click="showAgentDropdown = !showAgentDropdown"
            class="flex items-center gap-2 px-3 py-1.5 text-sm bg-muted border border-border rounded-lg hover:bg-card transition-colors text-foreground"
          >
            <Bot class="w-3.5 h-3.5 text-muted-foreground" />
            <span class="max-w-[120px] truncate">{{ selectedAgentName || '选择项目...' }}</span>
            <ChevronDown class="w-3.5 h-3.5 text-muted-foreground" />
          </button>

          <!-- 遮罩 -->
          <div v-if="showAgentDropdown" class="fixed inset-0 z-40" @click="showAgentDropdown = false"></div>

          <!-- 下拉面板 -->
          <Transition name="fade">
            <div
              v-if="showAgentDropdown"
              class="absolute right-0 top-full mt-1 w-52 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
            >
              <div class="px-3 py-2 border-b border-border">
                <span class="text-xs font-medium text-muted-foreground">选择项目</span>
              </div>
              <div class="max-h-48 overflow-y-auto scrollbar-thin">
                <div v-if="agentStore.agents.length === 0" class="px-4 py-3 text-xs text-muted-foreground/50 text-center">
                  暂无项目
                </div>
                <div
                  v-for="agent in agentStore.agents"
                  :key="agent.agent_id"
                  class="flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors"
                  :class="skillStore.selectedAgentId === agent.agent_id
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-muted text-foreground'"
                  @click="handleAgentSelect(agent.agent_id)"
                >
                  <Bot class="w-3.5 h-3.5 text-muted-foreground/50" />
                  <span class="text-sm truncate flex-1">{{ agent.name }}</span>
                  <CheckCircle
                    v-if="skillStore.selectedAgentId === agent.agent_id"
                    class="w-3.5 h-3.5 text-primary flex-shrink-0"
                  />
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <!-- 刷新 -->
        <button
          @click="handleRefresh"
          :disabled="skillStore.currentLoading"
          class="p-2 bg-muted border border-border rounded-lg text-muted-foreground hover:text-foreground transition-colors"
          title="刷新"
        >
          <RefreshCw class="w-4 h-4" :class="skillStore.currentLoading ? 'animate-spin' : ''" />
        </button>

        <!-- 上传（仅技能库 tab） -->
        <button
          v-if="skillStore.activeTab === 'library'"
          @click="showUploadModal = true"
          class="flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover transition-all shadow-sm active:scale-95"
        >
          <Upload class="w-4 h-4" />
          上传技能
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧列表 -->
      <div class="w-72 border-r border-border bg-muted/50 overflow-y-auto p-4 flex flex-col flex-shrink-0">
        <!-- 搜索框 -->
        <div class="relative mb-3 group">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50 group-focus-within:text-primary transition-colors" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索技能..."
            class="w-full pl-9 pr-4 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-primary/30 focus:border-primary/30 text-foreground placeholder:text-muted-foreground/50 transition-all"
          >
        </div>

        <!-- 项目技能 tab 未选择项目提示 -->
        <div v-if="skillStore.activeTab === 'project' && !skillStore.selectedAgentId" class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 py-12">
          <Bot class="w-8 h-8 mb-2 opacity-40" />
          <p class="text-xs text-center">请先选择一个项目<br>查看其已安装的技能</p>
        </div>

        <!-- 加载中 -->
        <div v-else-if="skillStore.currentLoading" class="flex items-center justify-center py-12 text-muted-foreground/50">
          <Loader2 class="w-5 h-5 animate-spin mr-2" />
          <span class="text-sm">加载中...</span>
        </div>

        <!-- 空状态 -->
        <div v-else-if="filteredSkills.length === 0" class="flex-1 flex flex-col items-center justify-center py-12">
          <div class="text-center text-muted-foreground/50">
            <Puzzle class="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p class="text-xs">
              <template v-if="searchQuery">未找到匹配的技能</template>
              <template v-else-if="skillStore.activeTab === 'project'">
                该项目暂未安装技能
                <button @click="handleSwitchTab('library')" class="block mx-auto mt-2 text-primary hover:underline">
                  去技能库安装
                </button>
              </template>
              <template v-else>暂无技能</template>
            </p>
          </div>
        </div>

        <!-- 技能列表 -->
        <div v-else class="space-y-1.5">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            @click="skillStore.selectSkill(skill)"
            class="p-3 rounded-lg cursor-pointer transition-all border"
            :class="skillStore.selectedSkill?.name === skill.name
              ? 'bg-card shadow-sm border-primary/20 ring-1 ring-primary/10'
              : 'bg-card/50 border-transparent hover:bg-card hover:border-border'"
          >
            <div class="flex items-start justify-between gap-2 mb-1">
              <h3 class="font-medium text-foreground text-sm truncate">{{ skill.name }}</h3>
              <span
                v-if="skill.status === 'need_setup'"
                class="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/15 text-primary font-medium"
              >需配置</span>
              <span
                v-else-if="skill.status === 'need_auth'"
                class="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium"
              >需授权</span>
              <span
                v-else-if="skill.status === 'unavailable'"
                class="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium"
              >不可用</span>
            </div>
            <p class="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{{ skill.description || '暂无描述' }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧详情区 -->
      <div class="flex-1 flex flex-col overflow-hidden bg-background">
        <!-- 未选中状态 -->
        <div v-if="!skillStore.selectedSkill" class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50">
          <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
            <Puzzle class="w-8 h-8 opacity-30" />
          </div>
          <p class="text-sm font-medium text-muted-foreground">选择一个技能查看详情</p>
        </div>

        <!-- 详情视图 -->
        <template v-else>
          <!-- 详情头部 -->
          <div class="h-14 flex items-center justify-between px-6 border-b border-border bg-background flex-shrink-0">
            <h2 class="text-base font-bold text-foreground">{{ skillStore.selectedSkill.name }}</h2>

            <div class="flex items-center gap-2">
              <!-- 技能库 tab：安装到项目 -->
              <template v-if="skillStore.activeTab === 'library'">
                <div class="relative" ref="installDropdownRef">
                  <button
                    @click="showInstallDropdown = !showInstallDropdown"
                    :disabled="skillStore.actionLoading || agentStore.agents.length === 0"
                    class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all disabled:opacity-50"
                  >
                    <Download class="w-4 h-4" />
                    安装到项目
                    <ChevronDown class="w-3.5 h-3.5" />
                  </button>

                  <!-- 安装下拉 -->
                  <div v-if="showInstallDropdown" class="fixed inset-0 z-40" @click="showInstallDropdown = false"></div>
                  <Transition name="fade">
                    <div
                      v-if="showInstallDropdown"
                      class="absolute right-0 top-full mt-1 w-56 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
                    >
                      <div class="px-3 py-2 border-b border-border">
                        <span class="text-xs font-medium text-muted-foreground">选择目标项目</span>
                      </div>
                      <div class="max-h-48 overflow-y-auto">
                        <div v-if="agentStore.agents.length === 0" class="px-4 py-3 text-xs text-muted-foreground/50 text-center">
                          暂无项目
                        </div>
                        <div
                          v-for="agent in agentStore.agents"
                          :key="agent.agent_id"
                          class="flex items-center gap-2 px-3 py-2.5 hover:bg-muted cursor-pointer transition-colors"
                          @click="handleInstall(agent.agent_id, agent.name)"
                        >
                          <Bot class="w-3.5 h-3.5 text-muted-foreground/50" />
                          <span class="text-sm text-foreground truncate">{{ agent.name }}</span>
                        </div>
                      </div>
                    </div>
                  </Transition>
                </div>
              </template>

              <!-- 项目技能 tab：卸载 -->
              <template v-if="skillStore.activeTab === 'project' && skillStore.selectedAgentId">
                <button
                  @click="handleUninstall"
                  :disabled="skillStore.actionLoading"
                  class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-destructive/30 text-destructive hover:bg-destructive/10 transition-all disabled:opacity-50"
                >
                  <Trash2 class="w-4 h-4" />
                  卸载
                </button>
              </template>
            </div>
          </div>

          <!-- 详情内容 -->
          <div class="flex-1 overflow-y-auto p-6 scrollbar-thin">
            <div class="max-w-4xl mx-auto space-y-5">
              <!-- 加载详情中 -->
              <div v-if="skillStore.detailLoading" class="flex items-center justify-center py-12 text-muted-foreground/50">
                <Loader2 class="w-5 h-5 animate-spin mr-2" />
                <span class="text-sm">加载详情中...</span>
              </div>

              <template v-else-if="skillStore.skillDetail">
                <!-- 基本信息 -->
                <div class="bg-muted/50 rounded-xl border border-border p-5">
                  <h3 class="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
                    <ClipboardList class="w-3.5 h-3.5" /> 基本信息
                  </h3>
                  <div class="space-y-3">
                    <div>
                      <label class="text-xs font-medium text-muted-foreground/70 mb-1 block">描述</label>
                      <p class="text-sm text-foreground leading-relaxed">{{ skillStore.skillDetail.description || '暂无描述' }}</p>
                    </div>
                    <div v-if="skillStore.skillDetail.preferred_for?.length">
                      <label class="text-xs font-medium text-muted-foreground/70 mb-1.5 block">适用场景</label>
                      <div class="flex flex-wrap gap-1.5">
                        <span
                          v-for="tag in skillStore.skillDetail.preferred_for"
                          :key="tag"
                          class="px-2.5 py-1 bg-accent text-accent-foreground border border-primary/10 rounded-md text-xs"
                        >
                          {{ tag }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- API Key 配置 -->
                <div
                  v-if="skillStore.skillDetail.required_env?.length"
                  class="bg-muted/50 rounded-xl border border-border p-5"
                  :class="{ 'border-primary/30 bg-primary/5': hasUnconfiguredEnv }"
                >
                  <h3 class="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
                    <Key class="w-3.5 h-3.5" /> API Key 配置
                    <span
                      v-if="hasUnconfiguredEnv"
                      class="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/15 text-primary font-medium normal-case tracking-normal"
                    >需配置</span>
                  </h3>
                  <div class="space-y-3">
                    <div
                      v-for="env in skillStore.skillDetail.required_env"
                      :key="env.name"
                      class="flex items-center gap-3"
                    >
                      <label class="text-xs font-medium text-muted-foreground w-40 flex-shrink-0 flex items-center gap-1.5">
                        {{ env.label }}
                        <CheckCircle v-if="env.is_set" class="w-3 h-3 text-success" />
                      </label>
                      <div class="relative flex-1">
                        <input
                          :type="showEnvSecrets[env.name] ? 'text' : 'password'"
                          v-model="envInputs[env.name]"
                          :placeholder="env.is_set ? '已配置（留空保持不变）' : `输入 ${env.label}`"
                          class="w-full px-3 py-1.5 text-xs border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow font-mono pr-8"
                        />
                        <button
                          @click="showEnvSecrets[env.name] = !showEnvSecrets[env.name]"
                          class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
                        >
                          <Eye v-if="!showEnvSecrets[env.name]" class="w-3 h-3" />
                          <EyeOff v-else class="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div class="flex items-center justify-end pt-1">
                      <button
                        @click="handleSaveConfig"
                        :disabled="!hasEnvInputs || configSaving"
                        class="flex items-center gap-1.5 px-4 py-1.5 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-all"
                      >
                        <Loader2 v-if="configSaving" class="w-3 h-3 animate-spin" />
                        保存配置
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 文件信息 -->
                <div v-if="skillStore.skillDetail.scripts?.length || skillStore.skillDetail.resources?.length" class="bg-muted/50 rounded-xl border border-border p-5">
                  <h3 class="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
                    <FolderOpen class="w-3.5 h-3.5" /> 文件结构
                  </h3>
                  <div class="grid grid-cols-2 gap-4">
                    <div>
                      <label class="text-xs font-medium text-muted-foreground/70 mb-2 block">脚本 (scripts/)</label>
                      <div class="space-y-1.5">
                        <div
                          v-for="script in skillStore.skillDetail.scripts"
                          :key="script"
                          @click="viewFile('scripts', script)"
                          class="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-lg text-xs text-muted-foreground font-mono cursor-pointer hover:border-primary/40 hover:bg-accent/50 transition-all group"
                        >
                          <FileCode class="w-3.5 h-3.5 text-primary" />
                          <span class="flex-1 truncate">{{ script }}</span>
                          <Eye class="w-3 h-3 text-muted-foreground/30 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <div v-if="!skillStore.skillDetail.scripts?.length" class="text-xs text-muted-foreground/40 italic px-3 py-2 bg-card/50 rounded-lg border border-dashed border-border">
                          无脚本文件
                        </div>
                      </div>
                    </div>
                    <div>
                      <label class="text-xs font-medium text-muted-foreground/70 mb-2 block">资源 (resources/)</label>
                      <div class="space-y-1.5">
                        <div
                          v-for="res in skillStore.skillDetail.resources"
                          :key="res"
                          @click="viewFile('resources', res)"
                          class="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-lg text-xs text-muted-foreground font-mono cursor-pointer hover:border-emerald-400/40 hover:bg-emerald-50/50 dark:hover:bg-emerald-900/10 transition-all group"
                        >
                          <FileJson class="w-3.5 h-3.5 text-emerald-500" />
                          <span class="flex-1 truncate">{{ res }}</span>
                          <Eye class="w-3 h-3 text-muted-foreground/30 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <div v-if="!skillStore.skillDetail.resources?.length" class="text-xs text-muted-foreground/40 italic px-3 py-2 bg-card/50 rounded-lg border border-dashed border-border">
                          无资源文件
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- SKILL.md 文档 -->
                <div v-if="skillStore.skillDetail.content" class="bg-card rounded-xl border border-border p-5">
                  <h3 class="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
                    <FileText class="w-3.5 h-3.5" /> SKILL.md 文档
                  </h3>
                  <div class="bg-muted rounded-lg p-4 border border-border max-h-[400px] overflow-y-auto scrollbar-thin">
                    <pre class="text-xs text-foreground/80 whitespace-pre-wrap font-mono leading-relaxed">{{ skillStore.skillDetail.content }}</pre>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 确认弹窗 -->
    <SimpleConfirmModal
      :show="confirmModal.show"
      :title="confirmModal.title"
      :message="confirmModal.message"
      :type="confirmModal.type"
      :confirm-text="confirmModal.confirmText"
      @confirm="confirmModal.onConfirm"
      @cancel="confirmModal.onCancel"
    />

    <!-- 操作结果提示（Teleport 到 body 避免被父容器 overflow 遮挡） -->
    <Teleport to="body">
      <Transition name="toast">
        <div
          v-if="toastMessage"
          class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] flex items-center gap-2 px-5 py-3 rounded-xl shadow-lg text-sm font-medium text-white"
          :style="{ backgroundColor: toastType === 'success' ? '#10b981' : '#ef4444' }"
        >
          <CheckCircle v-if="toastType === 'success'" class="w-4 h-4" />
          <AlertCircle v-else class="w-4 h-4" />
          {{ toastMessage }}
        </div>
      </Transition>
    </Teleport>

    <!-- 上传 Modal -->
    <Teleport to="body">
      <div
        v-if="showUploadModal"
        class="fixed inset-0 bg-foreground/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        @click.self="showUploadModal = false"
      >
        <div class="bg-card rounded-2xl shadow-2xl w-full max-w-md overflow-hidden border border-border">
          <div class="px-6 py-4 border-b border-border flex items-center justify-between">
            <h3 class="text-base font-bold text-foreground">上传新技能</h3>
            <button @click="showUploadModal = false" class="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="p-6 space-y-4">
            <div>
              <label class="text-sm font-medium text-foreground mb-2 block">技能名称</label>
              <input
                v-model="uploadSkillName"
                placeholder="例如: my-custom-skill"
                class="w-full px-3 py-2 border border-border rounded-lg text-sm bg-muted focus:outline-none focus:ring-1 focus:ring-primary/30 text-foreground"
              >
              <p class="text-xs text-muted-foreground/50 mt-1">只能包含小写字母、数字和连字符</p>
            </div>
            <div>
              <label class="text-sm font-medium text-foreground mb-2 block">上传 ZIP 文件</label>
              <div
                class="border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors cursor-pointer"
                @click="fileInput?.click()"
                @dragover.prevent
                @drop.prevent="handleFileDrop"
              >
                <Upload class="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
                <p class="text-sm text-muted-foreground">
                  {{ uploadFile ? uploadFile.name : '点击选择或拖拽文件' }}
                </p>
                <p class="text-xs text-muted-foreground/50 mt-1">ZIP 文件，必须包含 SKILL.md</p>
              </div>
              <input
                ref="fileInput"
                type="file"
                accept=".zip"
                @change="handleFileSelect"
                class="hidden"
              >
            </div>
          </div>
          <div class="px-6 py-4 border-t border-border flex justify-end gap-3 bg-muted/50">
            <button @click="showUploadModal = false" class="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">取消</button>
            <button
              @click="handleUpload"
              :disabled="!uploadSkillName || !uploadFile || skillStore.actionLoading"
              class="px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-all"
            >
              {{ skillStore.actionLoading ? '上传中...' : '上传' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 文件查看 Modal -->
    <Teleport to="body">
      <div
        v-if="showFileModal"
        class="fixed inset-0 bg-foreground/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        @click.self="showFileModal = false"
      >
        <div class="bg-card rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden flex flex-col border border-border">
          <!-- 头部 -->
          <div class="px-6 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center" :class="currentFileType === 'scripts' ? 'bg-accent' : 'bg-emerald-100 dark:bg-emerald-900/30'">
                <FileCode v-if="currentFileType === 'scripts'" class="w-4 h-4 text-primary" />
                <FileJson v-else class="w-4 h-4 text-emerald-500" />
              </div>
              <div>
                <h3 class="text-sm font-bold text-foreground">{{ currentFileName }}</h3>
                <p class="text-xs text-muted-foreground">
                  {{ currentFileType === 'scripts' ? '脚本文件' : '资源文件' }} · {{ skillStore.selectedSkill?.name }}
                </p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="fileContent && !fileContent.is_binary"
                @click="copyFileContent"
                class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted rounded-lg hover:text-foreground transition-colors"
              >
                <Copy class="w-3.5 h-3.5" />
                复制
              </button>
              <button @click="showFileModal = false" class="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- 内容 -->
          <div class="flex-1 overflow-hidden">
            <div v-if="fileLoading" class="flex items-center justify-center h-64 text-muted-foreground/50">
              <Loader2 class="w-5 h-5 animate-spin mr-2" /> 加载文件中...
            </div>
            <div v-else-if="fileContent?.is_binary" class="flex flex-col items-center justify-center h-64 text-muted-foreground/50">
              <FileWarning class="w-10 h-10 mb-3 opacity-30" />
              <p class="text-sm font-medium text-muted-foreground">此文件为二进制格式</p>
              <p class="text-xs mt-1">无法显示内容，文件大小: {{ formatFileSize(fileContent.size) }}</p>
            </div>
            <div v-else-if="fileContent" class="h-full overflow-auto">
              <div class="p-1">
                <div class="bg-gray-900 rounded-xl overflow-hidden">
                  <div class="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
                    <span class="text-xs font-medium text-gray-400">{{ fileContent.language?.toUpperCase() || 'TEXT' }}</span>
                    <span class="text-xs text-gray-500">{{ formatFileSize(fileContent.size) }}</span>
                  </div>
                  <pre class="p-4 text-sm text-gray-300 font-mono leading-relaxed overflow-auto max-h-[calc(85vh-180px)] whitespace-pre-wrap break-words"><code>{{ fileContent.content }}</code></pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSkillStore } from '@/stores/skill'
import { useAgentStore } from '@/stores/agent'
import * as skillsApi from '@/api/skills'
import type { SkillFileContentResponse } from '@/api/skills'
import SimpleConfirmModal from '@/components/modals/SimpleConfirmModal.vue'
import {
  Puzzle,
  Bot,
  Search,
  RefreshCw,
  Loader2,
  Trash2,
  ClipboardList,
  X,
  Upload,
  Download,
  ChevronDown,
  Key,
  Eye,
  EyeOff,
  FileCode,
  FileJson,
  FileText,
  FolderOpen,
  Copy,
  FileWarning,
  CheckCircle,
  AlertCircle,
  ArrowLeft
} from 'lucide-vue-next'

// ==================== Stores ====================

const skillStore = useSkillStore()
const agentStore = useAgentStore()
const route = useRoute()

// ==================== 本地状态 ====================

const searchQuery = ref('')

// 安装下拉
const showInstallDropdown = ref(false)
const installDropdownRef = ref<HTMLDivElement | null>(null)

// Agent 选择器下拉
const showAgentDropdown = ref(false)
const agentDropdownRef = ref<HTMLDivElement | null>(null)

/** 当前选中的 Agent 名称 */
const selectedAgentName = computed(() => {
  if (!skillStore.selectedAgentId) return ''
  const agent = agentStore.agents.find(a => a.agent_id === skillStore.selectedAgentId)
  return agent?.name || skillStore.selectedAgentId
})

// 上传 Modal
const showUploadModal = ref(false)
const uploadSkillName = ref('')
const uploadFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// 文件查看 Modal
const showFileModal = ref(false)
const fileLoading = ref(false)
const currentFileType = ref<'scripts' | 'resources'>('scripts')
const currentFileName = ref('')
const fileContent = ref<SkillFileContentResponse | null>(null)

// API Key 配置
const envInputs = ref<Record<string, string>>({})
const showEnvSecrets = ref<Record<string, boolean>>({})
const configSaving = ref(false)

const hasUnconfiguredEnv = computed(() => {
  return skillStore.skillDetail?.required_env?.some(e => !e.is_set) ?? false
})

const hasEnvInputs = computed(() => {
  return Object.values(envInputs.value).some(v => v.trim())
})

// Toast 提示
const toastMessage = ref('')
const toastType = ref<'success' | 'error'>('success')
let toastTimer: ReturnType<typeof setTimeout> | null = null

// 确认弹窗
const confirmModal = reactive({
  show: false,
  title: '确认操作',
  message: '',
  type: 'warning' as 'confirm' | 'warning' | 'info' | 'error',
  confirmText: '确定',
  onConfirm: () => {},
  onCancel: () => { confirmModal.show = false },
})

/** Promise 化的确认弹窗 */
function showConfirm(options: {
  title?: string
  message: string
  type?: 'confirm' | 'warning' | 'info' | 'error'
  confirmText?: string
}): Promise<boolean> {
  return new Promise((resolve) => {
    confirmModal.title = options.title || '确认操作'
    confirmModal.message = options.message
    confirmModal.type = options.type || 'warning'
    confirmModal.confirmText = options.confirmText || '确定'
    confirmModal.onConfirm = () => {
      confirmModal.show = false
      resolve(true)
    }
    confirmModal.onCancel = () => {
      confirmModal.show = false
      resolve(false)
    }
    confirmModal.show = true
  })
}

// ==================== 计算属性 ====================

const filteredSkills = computed(() => {
  const list = skillStore.currentSkills
  if (!searchQuery.value) return list
  const query = searchQuery.value.toLowerCase()
  return list.filter(skill =>
    skill.name.toLowerCase().includes(query) ||
    skill.description.toLowerCase().includes(query)
  )
})

// ==================== Tab 与数据 ====================

function handleSwitchTab(tab: 'library' | 'project') {
  searchQuery.value = ''
  skillStore.switchTab(tab)
  if (tab === 'library' && skillStore.globalSkills.length === 0) {
    skillStore.fetchGlobal()
  }
}

function handleAgentSelect(agentId: string) {
  showAgentDropdown.value = false
  if (agentId) {
    skillStore.fetchProjectSkills(agentId)
  }
}

function handleRefresh() {
  if (skillStore.activeTab === 'library') {
    skillStore.fetchGlobal()
  } else if (skillStore.selectedAgentId) {
    skillStore.fetchProjectSkills(skillStore.selectedAgentId)
  }
}

// ==================== 安装/卸载/启停 ====================

async function handleInstall(agentId: string, agentName: string) {
  if (!skillStore.selectedSkill) return
  showInstallDropdown.value = false

  try {
    const result = await skillStore.install(skillStore.selectedSkill.name, agentId)
    if (result.success) {
      showToast(`已安装到 "${agentName}"`, 'success')
    } else {
      showToast(result.message || '安装失败', 'error')
    }
  } catch (error: any) {
    console.error('handleInstall 异常:', error)
    const msg = error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || error?.message
      || '安装失败'
    showToast(typeof msg === 'string' ? msg : '安装失败', 'error')
  }
}

async function handleUninstall() {
  if (!skillStore.selectedSkill || !skillStore.selectedAgentId) return
  const name = skillStore.selectedSkill.name

  const confirmed = await showConfirm({
    title: '卸载技能',
    message: `确定要从该项目卸载 "${name}" 吗？`,
    type: 'warning',
    confirmText: '卸载',
  })
  if (!confirmed) return

  const result = await skillStore.uninstall(name, skillStore.selectedAgentId)
  if (result.success) {
    showToast(`"${name}" 已卸载`, 'success')
  } else {
    showToast(result.message, 'error')
  }
}

// ==================== API Key 配置 ====================

async function handleSaveConfig() {
  const detail = skillStore.skillDetail
  if (!detail) return

  // Filter out empty inputs
  const vars: Record<string, string> = {}
  for (const [key, val] of Object.entries(envInputs.value)) {
    if (val.trim()) vars[key] = val.trim()
  }
  if (!Object.keys(vars).length) return

  configSaving.value = true
  try {
    const result = await skillsApi.configureSkill({
      skill_name: detail.name,
      agent_id: detail.agent_id || 'global',
      env_vars: vars,
    })
    if (result.success) {
      showToast(result.message || '配置已保存', 'success')
      // Clear inputs and refresh detail
      envInputs.value = {}
      await skillStore.reloadDetail(detail.name, detail.agent_id !== 'global' ? detail.agent_id : undefined)
    } else {
      showToast('保存失败', 'error')
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '保存失败'
    showToast(msg, 'error')
  } finally {
    configSaving.value = false
  }
}

// ==================== 上传 ====================

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    uploadFile.value = input.files[0]
  }
}

function handleFileDrop(event: DragEvent) {
  if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
    const file = event.dataTransfer.files[0]
    if (file.name.endsWith('.zip')) {
      uploadFile.value = file
    } else {
      showToast('请上传 .zip 文件', 'error')
    }
  }
}

async function handleUpload() {
  if (!uploadSkillName.value || !uploadFile.value) return

  const result = await skillStore.uploadToGlobal(uploadFile.value, uploadSkillName.value)
  if (result.success) {
    showToast('上传成功', 'success')
    showUploadModal.value = false
    uploadSkillName.value = ''
    uploadFile.value = null
  } else {
    showToast(result.message, 'error')
  }
}

// ==================== 文件查看 ====================

async function viewFile(fileType: 'scripts' | 'resources', fileName: string) {
  if (!skillStore.selectedSkill) return

  currentFileType.value = fileType
  currentFileName.value = fileName
  fileContent.value = null
  showFileModal.value = true
  fileLoading.value = true

  try {
    const agentId = skillStore.activeTab === 'project' ? skillStore.selectedAgentId || undefined : undefined
    fileContent.value = await skillsApi.getSkillFileContent(
      skillStore.selectedSkill.name,
      fileType,
      fileName,
      agentId
    )
  } catch (error) {
    console.error('获取文件内容失败:', error)
    showToast('获取文件内容失败', 'error')
    showFileModal.value = false
  } finally {
    fileLoading.value = false
  }
}

async function copyFileContent() {
  if (!fileContent.value?.content) return
  try {
    await navigator.clipboard.writeText(fileContent.value.content)
    showToast('已复制到剪贴板', 'success')
  } catch {
    showToast('复制失败', 'error')
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ==================== Toast ====================

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  console.log('[Toast]', type, msg)
  toastMessage.value = msg
  toastType.value = type
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMessage.value = '' }, 3000)
}

// ==================== 生命周期 ====================

onMounted(async () => {
  // 初始加载全局技能库
  await skillStore.fetchGlobal()
  // 确保 Agent 列表已加载（项目技能 tab 需要）
  if (agentStore.agents.length === 0) {
    await agentStore.fetchList()
  }

  // 如果路由带了 tab 和 agent 参数，自动切换
  const tab = route.query.tab as string
  const agentId = route.query.agent as string
  if (tab === 'project') {
    skillStore.switchTab('project')
    if (agentId) {
      await skillStore.fetchProjectSkills(agentId)
    }
  }
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

<!-- Toast 过渡动画：Teleport 到 body 后 scoped 样式不生效，必须用全局样式 -->
<style>
.toast-enter-active {
  transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translate(-50%, 8px);
}
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 4px);
}
</style>
