<template>
  <div class="admin-panel">
    <!-- 顶部栏 -->
    <header class="admin-header">
      <div class="admin-header-left">
        <button class="back-btn" @click="handleBack" title="返回地图" aria-label="返回巡礼地图">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <h1 class="admin-title">巡礼数据中心</h1>
        <span class="admin-subtitle">知识库管理与审核后台</span>
      </div>
      <div class="admin-header-right">
        <span class="status-text">ANIME ATLAS / WORKSPACE</span>
      </div>
    </header>

    <div class="admin-body">
      <!-- 左侧导航 -->
      <nav class="admin-nav">
        <button
          v-for="tab in navTabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="handleTabSwitch(tab.key)"
        >
          <el-icon :size="18"><component :is="tab.icon" /></el-icon>
          <span class="nav-label">{{ tab.label }}</span>
          <span v-if="tab.key === 'pending' && pendingList.length > 0" class="nav-badge">
            {{ pendingList.length }}
          </span>
        </button>
      </nav>

      <!-- 右侧内容区 -->
      <main class="admin-main">
        <!-- ============ Tab 1: 待审核切片 ============ -->
        <div v-if="activeTab === 'pending'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">待审核切片</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingPending" @click="fetchPending">
                <el-icon v-if="!loadingPending"><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>

          <div v-if="loadingPending" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>加载待审核队列...</span>
          </div>

          <div v-else-if="pendingList.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><CircleCheck /></el-icon>
            <h3 class="empty-title">队列为空</h3>
            <p class="empty-desc">当前没有待审核的地标切片，所有数据均已处理完毕。</p>
          </div>

          <div v-else class="pending-grid">
            <div
              v-for="item in pendingList"
              :key="item.id"
              class="pending-card"
              :class="{ selected: selectedPendingId === item.id }"
              @click="selectPending(item)"
            >
              <div class="pending-card-header">
                <span class="pending-name">{{ item.landmark_name }}</span>
                <el-tag size="small" type="warning" effect="plain">{{ item.chunks?.length || 0 }} 切片</el-tag>
              </div>
              <div class="pending-card-meta">
                <span class="pending-bangumi">{{ item.bangumi }}</span>
                <span class="pending-time">{{ item.timestamp }}</span>
              </div>
              <div class="pending-sources" v-if="item.sources?.length">
                <span class="source-label">来源:</span>
                <span v-for="(src, i) in item.sources.slice(0, 2)" :key="i" class="source-url" :title="src">
                  {{ formatUrl(src) }}
                </span>
                <span v-if="item.sources.length > 2" class="source-more">+{{ item.sources.length - 2 }}</span>
              </div>
            </div>
          </div>

          <!-- 切片编辑区 -->
          <div v-if="selectedPending" class="chunk-editor-section">
            <div class="editor-header">
              <h3 class="editor-title">
                <el-icon><Edit /></el-icon>
                编辑切片: {{ selectedPending.landmark_name }}
              </h3>
              <div class="editor-actions">
                <el-button size="small" @click="addChunk">
                  <el-icon><Plus /></el-icon>
                  新增切片
                </el-button>
              </div>
            </div>

            <div class="chunks-list scrollbar-wrapper">
              <div
                v-for="(chunk, idx) in editingChunks"
                :key="idx"
                class="chunk-card"
              >
                <div class="chunk-card-header">
                  <span class="chunk-index">切片 #{{ idx + 1 }}</span>
                  <el-button
                    text
                    size="small"
                    type="danger"
                    @click="removeChunk(idx)"
                    title="删除此切片"
                  >
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-input
                  v-model="editingChunks[idx]"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 8 }"
                  resize="vertical"
                />
              </div>
            </div>

            <div class="editor-footer">
              <el-button
                type="danger"
                plain
                @click="handleReject"
                :loading="actionLoading"
              >
                <el-icon><CircleClose /></el-icon>
                拒绝写入
              </el-button>
              <el-button
                type="primary"
                @click="handleApprove"
                :loading="actionLoading"
              >
                <el-icon><CircleCheck /></el-icon>
                同意并写入 Chroma
              </el-button>
            </div>
          </div>
        </div>

        <!-- ============ Tab 2: 已入库地标 ============ -->
        <div v-if="activeTab === 'database'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">已入库地标</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingLandmarks" @click="fetchLandmarks">
                <el-icon v-if="!loadingLandmarks"><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button size="small" type="danger" plain @click="handleClearDatabase">
                <el-icon><Delete /></el-icon>
                清空数据库
              </el-button>
            </div>
          </div>

          <div v-if="loadingLandmarks" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>加载地标数据...</span>
          </div>

          <div v-else-if="dbLandmarks.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Files /></el-icon>
            <h3 class="empty-title">数据库为空</h3>
            <p class="empty-desc">向量数据库中暂无已入库的地标数据。请先在坐标库中选中地标并生成路线，然后在"待审核切片"中批准写入。</p>
          </div>

          <div v-else>
            <div class="db-stats-bar">
              <div class="stat-item">
                <span class="stat-value">{{ dbLandmarks.length }}</span>
                <span class="stat-label">地标总数</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ totalDbChunks }}</span>
                <span class="stat-label">切片总数</span>
              </div>
            </div>

            <div class="db-landmark-list">
              <div
                v-for="lm in dbLandmarks"
                :key="lm.id"
                class="db-landmark-card"
              >
                <div class="db-lm-main" @click="toggleLandmarkExpand(lm.id)">
                  <div class="db-lm-info">
                    <span class="db-lm-name">{{ lm.name }}</span>
                    <span class="db-lm-bangumi">{{ lm.bangumi }}</span>
                  </div>
                  <div class="db-lm-right">
                    <el-tag size="small" effect="plain">{{ lm.chunks_count }} Chunks</el-tag>
                    <el-button
                      text
                      size="small"
                      type="danger"
                      @click.stop="handleDeleteLandmark(lm.id, lm.name)"
                      title="从数据库中删除"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                    <el-icon class="expand-arrow" :class="{ rotated: expandedLandmarkId === lm.id }">
                      <ArrowRight />
                    </el-icon>
                  </div>
                </div>

                <!-- 展开查看切片 -->
                <div v-if="expandedLandmarkId === lm.id" class="db-lm-detail">
                  <div v-if="loadingChunks" class="loading-state compact">
                    <el-icon class="is-loading"><Loading /></el-icon>
                    <span>加载切片数据...</span>
                  </div>
                  <div v-else-if="expandedChunks.length === 0" class="detail-empty">
                    暂无切片数据
                  </div>
                  <div v-else class="detail-chunk-list">
                    <div v-for="(chunk, idx) in expandedChunks" :key="chunk.id" class="detail-chunk-item">
                      <span class="chunk-idx">切片 #{{ idx + 1 }}</span>
                      <p class="chunk-text">{{ chunk.content }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ Tab 3: 运行日志 ============ -->
        <div v-if="activeTab === 'logs'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">运行日志</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingLogs" @click="fetchLogs">
                <el-icon v-if="!loadingLogs"><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button size="small" type="danger" plain @click="handleClearLogs">
                <el-icon><Delete /></el-icon>
                清空日志
              </el-button>
            </div>
          </div>

          <div v-if="loadingLogs" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>读取运行日志...</span>
          </div>

          <div v-else-if="logs.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Clock /></el-icon>
            <h3 class="empty-title">暂无运行日志</h3>
            <p class="empty-desc">系统尚未进行地标录入 (ingest)、审核 (pending)、拒绝 (reject) 或召回 (recall) 操作。</p>
          </div>

          <div v-else class="logs-list">
            <div
              v-for="(log, idx) in logs"
              :key="log.timestamp + '_' + idx"
              class="log-card"
              :class="log.event_type"
            >
              <div class="log-header" @click="toggleLogExpand(idx)">
                <div class="log-header-left">
                  <el-tag
                    size="small"
                    :type="getLogTagType(log.event_type)"
                    effect="dark"
                    class="log-type-tag"
                  >
                    {{ getLogLabel(log.event_type) }}
                  </el-tag>
                  <span class="log-title">
                    <template v-if="log.event_type === 'ingest'">
                      录入 {{ log.landmarks_count }} 个地标 ({{ log.total_chunks_added }} 分块)
                    </template>
                    <template v-else-if="log.event_type === 'recall'">
                      检索: "{{ log.query }}"
                    </template>
                    <template v-else-if="log.event_type === 'pending'">
                      暂存: {{ log.landmark_name }} ({{ log.chunks_count }} 切片)
                    </template>
                    <template v-else-if="log.event_type === 'reject'">
                      拒绝: {{ log.pending_id }}
                    </template>
                    <template v-else-if="log.event_type === 'delete'">
                      删除: {{ log.landmark_id }} ({{ log.chunks_deleted }} 切片)
                    </template>
                    <template v-else>
                      {{ log.event_type }}
                    </template>
                  </span>
                </div>
                <div class="log-header-right">
                  <span class="log-time">{{ log.timestamp }}</span>
                  <el-icon class="log-arrow" :class="{ rotated: expandedLogIdx === idx }">
                    <ArrowRight />
                  </el-icon>
                </div>
              </div>

              <div v-if="expandedLogIdx === idx" class="log-detail">
                <!-- 写入详情 -->
                <template v-if="log.event_type === 'ingest'">
                  <div v-for="item in log.details" :key="item.landmark_id" class="detail-section">
                    <div class="detail-section-title">
                      地标: <strong>{{ item.landmark_name }}</strong> ({{ item.bangumi }})
                      <span class="chunks-badge">{{ item.chunks_count }} 个切片</span>
                    </div>
                    <div class="detail-chunk-list">
                      <div v-for="(chunk, cIdx) in item.chunks" :key="cIdx" class="detail-chunk-item">
                        <span class="chunk-idx">切片 #{{ cIdx + 1 }}</span>
                        <p class="chunk-text">{{ chunk }}</p>
                      </div>
                    </div>
                  </div>
                </template>

                <!-- 召回详情 -->
                <template v-else-if="log.event_type === 'recall'">
                  <div v-if="log.error" class="detail-error">
                    <span class="error-label">错误:</span>
                    <span class="error-text">{{ log.error }}</span>
                  </div>
                  <template v-else>
                    <div class="detail-section">
                      <div class="detail-section-title">
                        Chroma 粗回文本数: <strong>{{ log.recalled_count }}</strong>
                      </div>
                    </div>
                    <div class="detail-section">
                      <div class="detail-section-title">精排 Top 3 文本块:</div>
                      <div class="detail-chunk-list">
                        <div v-for="chunk in log.reranked_top_3" :key="chunk.rank" class="detail-chunk-item">
                          <div class="chunk-header-row">
                            <span class="chunk-idx">Top #{{ chunk.rank }} (评分: {{ chunk.score === -1 ? '相似度' : chunk.score.toFixed(3) }})</span>
                            <span class="chunk-source-tag">{{ chunk.landmark_name }} - {{ chunk.bangumi }}</span>
                          </div>
                          <p class="chunk-text">{{ chunk.content }}</p>
                        </div>
                      </div>
                    </div>
                    <div class="detail-section">
                      <div class="detail-section-title">注入模型 Prompt 的完整 RAG Context:</div>
                      <pre class="context-pre">{{ log.final_context || '(无数据)' }}</pre>
                    </div>
                  </template>
                </template>

                <!-- 其他事件的 raw JSON -->
                <template v-else>
                  <pre class="context-pre">{{ JSON.stringify(log, null, 2) }}</pre>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ Tab 4: 召回测试 ============ -->
        <div v-if="activeTab === 'recall'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">召回测试</h2>
          </div>

          <div class="recall-search-bar">
            <el-input
              v-model="recallQuery"
              placeholder="输入关键词进行向量召回 + Reranker 精排测试..."
              size="large"
              clearable
              @keyup.enter="handleRecallSearch"
            >
              <template #append>
                <el-button @click="handleRecallSearch" :loading="recallSearching">
                  <el-icon v-if="!recallSearching"><Search /></el-icon>
                  检索
                </el-button>
              </template>
            </el-input>
          </div>

          <div v-if="recallSearching" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>检索与精排中...</span>
          </div>

          <div v-else-if="recallSearched && recallResults.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Warning /></el-icon>
            <h3 class="empty-title">未召回相关文本</h3>
            <p class="empty-desc">请尝试更换查询词，或确保数据库中已录入相关作品的数据。</p>
          </div>

          <div v-else-if="!recallSearched" class="empty-state">
            <el-icon :size="48" class="empty-icon"><ChatLineRound /></el-icon>
            <h3 class="empty-title">召回与重排测试</h3>
            <p class="empty-desc">输入关键词后，系统会从向量数据库中召回候选文本块，并由 Reranker 模型重新打分排序。你可以用这个工具来验证知识库的检索精度。</p>
          </div>

          <div v-else class="recall-results">
            <div class="recall-meta">
              召回并精排前 <strong>{{ recallResults.length }}</strong> 条结果
            </div>
            <div class="recall-cards">
              <div
                v-for="item in recallResults"
                :key="item.rank"
                class="recall-card"
              >
                <div class="recall-card-header">
                  <div class="recall-left">
                    <span class="recall-rank">#{{ item.rank }}</span>
                    <span class="recall-source">{{ item.landmark_name }} ({{ item.bangumi }})</span>
                  </div>
                  <el-tag
                    size="small"
                    :type="getScoreType(item.score)"
                    effect="dark"
                  >
                    {{ item.score === -1 ? '相似度' : '分: ' + item.score.toFixed(3) }}
                  </el-tag>
                </div>
                <p class="recall-content">{{ item.content }}</p>
                <div class="recall-footer" v-if="item.source && item.source !== '未知来源'">
                  <span class="source-label">来源:</span>
                  <span class="source-val">{{ item.source }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ Tab 5: Agent 追踪 ============ -->
        <div v-if="activeTab === 'agent'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">Agent 调用追踪</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingTraces" @click="fetchAgentTraces">
                <el-icon v-if="!loadingTraces"><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button size="small" type="danger" plain @click="handleClearTraces">
                <el-icon><Delete /></el-icon>
                清空记录
              </el-button>
            </div>
          </div>

          <p class="agent-tip">
            <el-icon><InfoFilled /></el-icon>
            点击左侧任意 Run 查看每个节点中所有模型 / 工具的输入输出。Run 按时间倒序，最近 50 条。
          </p>

          <div class="agent-layout">
            <!-- 左侧：Run 列表 -->
            <aside class="agent-runs-pane">
              <div v-if="loadingTraces" class="loading-state compact">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载追踪记录...</span>
              </div>
              <div v-else-if="agentTraces.length === 0" class="empty-state compact">
                <el-icon :size="36" class="empty-icon"><Cpu /></el-icon>
                <p class="empty-desc">暂无 Agent 调用记录。<br/>触发一次「Agent 路线规划」即可看到记录。</p>
              </div>
              <div v-else class="agent-runs-list">
                <div
                  v-for="run in agentTraces"
                  :key="run.run_id"
                  class="agent-run-card"
                  :class="{
                    active: selectedRunId === run.run_id,
                    error: run.status === 'error',
                    running: run.status === 'running'
                  }"
                  @click="selectAgentRun(run.run_id)"
                >
                  <div class="run-card-header">
                    <el-tag size="small" :type="getRunStatusType(run.status)" effect="dark">
                      {{ getRunStatusLabel(run.status) }}
                    </el-tag>
                    <span class="run-steps-count">{{ run.step_count }} 步</span>
                  </div>
                  <div class="run-card-meta">
                    <span class="run-days">{{ run.days }} 日</span>
                    <span class="run-time">{{ formatRunTime(run.start_time) }}</span>
                    <span v-if="run.duration_ms" class="run-time">{{ formatDuration(run.duration_ms) }}</span>
                  </div>
                  <div v-if="(run.tool_names || []).length" class="run-card-tools" :title="run.tool_names.join('，')">
                    工具: {{ run.tool_names.slice(0, 2).join('、') }}
                    <span v-if="run.tool_names.length > 2">+{{ run.tool_names.length - 2 }}</span>
                  </div>
                  <div class="run-card-landmarks" :title="(run.landmark_names || []).join('，')">
                    {{ (run.landmark_names || []).slice(0, 3).join('、') }}
                    <span v-if="(run.landmark_names || []).length > 3" class="more-tag">
                      +{{ run.landmark_names.length - 3 }}
                    </span>
                  </div>
                  <div v-if="run.error" class="run-card-error" :title="run.error">
                    错误: {{ run.error.slice(0, 60) }}
                  </div>
                </div>
              </div>
            </aside>

            <!-- 右侧：选中 Run 的详情 -->
            <section class="agent-detail-pane">
              <div v-if="loadingTraceDetail" class="loading-state">
                <el-icon class="is-loading" :size="24"><Loading /></el-icon>
                <span>加载步骤详情...</span>
              </div>

              <div v-else-if="!selectedTrace" class="empty-state">
                <el-icon :size="48" class="empty-icon"><ChatDotRound /></el-icon>
                <h3 class="empty-title">请选择一次 Run</h3>
                <p class="empty-desc">在左侧列表中选择 Run 查看每一步模型 / 工具的输入输出。</p>
              </div>

              <div v-else class="agent-trace-content">
                <!-- Run 概览 -->
                <div class="trace-overview">
                  <div class="overview-row">
                    <span class="overview-label">Run ID:</span>
                    <code class="overview-code">{{ selectedTrace.run_id }}</code>
                  </div>
                  <div class="overview-row">
                    <span class="overview-label">开始:</span>
                    <span>{{ selectedTrace.start_time }}</span>
                    <span class="overview-label" style="margin-left: 16px;">结束:</span>
                    <span>{{ selectedTrace.end_time || '运行中' }}</span>
                  </div>
                  <div class="overview-row">
                    <span class="overview-label">天数:</span>
                    <span>{{ selectedTrace.days }}</span>
                    <span class="overview-label" style="margin-left: 16px;">步骤总数:</span>
                    <span>{{ (selectedTrace.steps || []).length }}</span>
                    <span class="overview-label" style="margin-left: 16px;">耗时:</span>
                    <span>{{ selectedTrace.duration_ms ? formatDuration(selectedTrace.duration_ms) : '-' }}</span>
                  </div>
                  <div v-if="(selectedTrace.tool_names || []).length" class="overview-row">
                    <span class="overview-label">工具:</span>
                    <span>{{ selectedTrace.tool_names.join('，') }}</span>
                  </div>
                  <div v-if="selectedTrace.error" class="overview-error">
                    错误: {{ selectedTrace.error }}
                  </div>
                </div>

                <!-- 按节点分组的步骤 -->
                <div
                  v-for="(group, gIdx) in groupedSteps"
                  :key="gIdx"
                  class="node-group"
                >
                  <div class="node-group-header">
                    <el-icon class="node-group-icon"><MagicStick /></el-icon>
                    <span class="node-group-name">{{ group.node }}</span>
                    <span class="node-group-count">{{ group.steps.length }} 步</span>
                  </div>

                  <div class="step-timeline">
                    <div
                      v-for="(step, sIdx) in group.steps"
                      :key="sIdx"
                      class="step-item"
                      :class="`step-${step.type}`"
                    >
                      <div class="step-marker">
                        <el-icon v-if="step.type === 'llm_call'"><ChatDotRound /></el-icon>
                        <el-icon v-else-if="step.type === 'tool_call'"><ToolsIcon /></el-icon>
                        <el-icon v-else-if="step.type === 'status'"><InfoFilled /></el-icon>
                        <el-icon v-else><MagicStick /></el-icon>
                      </div>

                      <div class="step-body" @click="toggleStep(step._id)">
                        <div class="step-header">
                          <el-tag size="small" :type="getStepTagType(step.type)" effect="plain">
                            {{ getStepTypeLabel(step.type) }}
                          </el-tag>
                          <span class="step-title">
                            <template v-if="step.type === 'llm_call'">{{ step.label }}</template>
                            <template v-else-if="step.type === 'tool_call'">
                              {{ step.tool }}
                              <span v-if="step.error" class="step-error-tag">出错</span>
                            </template>
                            <template v-else-if="step.type === 'event'">{{ step.title }}</template>
                            <template v-else-if="step.type === 'status'">{{ step.message }}</template>
                            <template v-else>{{ step.summary || step.type }}</template>
                          </span>
                          <span class="step-time">{{ step.timestamp?.split(' ')[1] }}</span>
                          <el-icon
                            v-if="isExpandableStep(step)"
                            class="step-arrow"
                            :class="{ rotated: expandedSteps[step._id] }"
                          >
                            <ArrowRight />
                          </el-icon>
                        </div>
                        <div v-if="getStepPreview(step)" class="step-preview">
                          {{ getStepPreview(step) }}
                        </div>

                        <!-- 展开的输入/输出 -->
                        <div v-if="expandedSteps[step._id]" class="step-detail" @click.stop>
                          <template v-if="step.type === 'llm_call'">
                            <div class="io-block">
                              <div class="io-label">
                                <span>📥 输入 Prompt</span>
                                <span class="io-meta">model: {{ step.model }}</span>
                                <button class="copy-btn" @click="copyText(getPromptText(step.prompt))">复制</button>
                              </div>
                              <pre class="io-pre">{{ getPromptText(step.prompt) }}</pre>
                            </div>
                            <div class="io-block">
                              <div class="io-label">
                                <span>📤 输出 Response</span>
                                <button class="copy-btn" @click="copyText(step.response)">复制</button>
                              </div>
                              <pre class="io-pre">{{ step.response }}</pre>
                            </div>
                          </template>

                          <template v-else-if="step.type === 'tool_call'">
                            <div class="io-block">
                              <div class="io-label">
                                <span>📥 参数 Args</span>
                                <button class="copy-btn" @click="copyText(JSON.stringify(step.args, null, 2))">复制</button>
                              </div>
                              <pre class="io-pre">{{ JSON.stringify(step.args, null, 2) }}</pre>
                            </div>
                            <div class="io-block">
                              <div class="io-label">
                                <span>📤 结果 Result</span>
                                <button class="copy-btn" @click="copyText(formatStepResult(step.result))">复制</button>
                              </div>
                              <pre class="io-pre">{{ formatStepResult(step.result) }}</pre>
                            </div>
                            <div v-if="step.error" class="io-block">
                              <div class="io-label io-label-error">⚠️ 错误</div>
                              <pre class="io-pre io-pre-error">{{ step.error }}</pre>
                            </div>
                          </template>

                          <template v-else-if="step.type === 'event'">
                            <div class="io-block">
                              <div class="io-label">
                                <span>调试事件</span>
                                <span class="io-meta">level: {{ step.level || 'info' }}</span>
                                <button class="copy-btn" @click="copyText(JSON.stringify(step.details || {}, null, 2))">复制</button>
                              </div>
                              <pre class="io-pre">{{ JSON.stringify(step.details || {}, null, 2) }}</pre>
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, markRaw } from 'vue'
import {
  ArrowLeft, ArrowRight, Refresh, Delete, Edit, Plus, Search,
  Loading, CircleCheck, CircleClose, Files, Clock, Warning,
  ChatLineRound, List, DataAnalysis, Document, Monitor,
  Cpu, MagicStick, Tools as ToolsIcon, ChatDotRound, InfoFilled
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app'

const store = useAppStore()

// ---- 导航 ----
const navTabs = [
  { key: 'pending', label: '待审核切片', icon: markRaw(Document) },
  { key: 'database', label: '已入库地标', icon: markRaw(DataAnalysis) },
  { key: 'logs', label: '运行日志', icon: markRaw(Clock) },
  { key: 'recall', label: '召回测试', icon: markRaw(Monitor) },
  { key: 'agent', label: 'Agent 追踪', icon: markRaw(Cpu) }
]
const activeTab = ref('pending')

function handleBack() {
  store.showAdminPage = false
}

function handleTabSwitch(key) {
  activeTab.value = key
  if (key === 'pending') fetchPending()
  else if (key === 'database') fetchLandmarks()
  else if (key === 'logs') fetchLogs()
  else if (key === 'agent') fetchAgentTraces()
}

// ---- 待审核 ----
const pendingList = ref([])
const loadingPending = ref(false)
const selectedPendingId = ref(null)
const editingChunks = ref([])
const actionLoading = ref(false)

const selectedPending = computed(() => pendingList.value.find(p => p.id === selectedPendingId.value))

async function fetchPending() {
  loadingPending.value = true
  try {
    const resp = await fetch('/api/rag/pending')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    pendingList.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取待审核队列失败: ${e.message}`)
  } finally {
    loadingPending.value = false
  }
}

function selectPending(item) {
  selectedPendingId.value = item.id
  editingChunks.value = [...(item.chunks || [])]
}

function addChunk() {
  editingChunks.value.push('')
}

function removeChunk(idx) {
  editingChunks.value.splice(idx, 1)
}

async function handleApprove() {
  if (!selectedPendingId.value) return
  // 过滤掉空切片
  const validChunks = editingChunks.value.filter(c => c.trim())
  if (validChunks.length === 0) {
    ElMessage.warning('请至少保留一个有效切片')
    return
  }
  actionLoading.value = true
  try {
    const resp = await fetch('/api/rag/pending/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedPendingId.value, chunks: validChunks })
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('切片已成功写入向量数据库')
    selectedPendingId.value = null
    editingChunks.value = []
    await fetchPending()
  } catch (e) {
    ElMessage.error(`审批写入失败: ${e.message}`)
  } finally {
    actionLoading.value = false
  }
}

async function handleReject() {
  if (!selectedPendingId.value) return
  try {
    await ElMessageBox.confirm(
      `确定要拒绝并删除地标"${selectedPending.value?.landmark_name}"的所有暂存切片吗？`,
      '拒绝确认',
      { confirmButtonText: '确定拒绝', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }

  actionLoading.value = true
  try {
    const resp = await fetch('/api/rag/pending/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedPendingId.value })
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('已拒绝并删除暂存记录')
    selectedPendingId.value = null
    editingChunks.value = []
    await fetchPending()
  } catch (e) {
    ElMessage.error(`拒绝操作失败: ${e.message}`)
  } finally {
    actionLoading.value = false
  }
}

// ---- 已入库地标 ----
const dbLandmarks = ref([])
const loadingLandmarks = ref(false)
const expandedLandmarkId = ref(null)
const expandedChunks = ref([])
const loadingChunks = ref(false)

const totalDbChunks = computed(() => dbLandmarks.value.reduce((sum, lm) => sum + (lm.chunks_count || 0), 0))

async function fetchLandmarks() {
  loadingLandmarks.value = true
  try {
    const resp = await fetch('/api/rag/landmarks')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    dbLandmarks.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取已入库地标失败: ${e.message}`)
  } finally {
    loadingLandmarks.value = false
  }
}

async function toggleLandmarkExpand(lmId) {
  if (expandedLandmarkId.value === lmId) {
    expandedLandmarkId.value = null
    expandedChunks.value = []
    return
  }
  expandedLandmarkId.value = lmId
  loadingChunks.value = true
  try {
    const resp = await fetch(`/api/rag/landmark/${encodeURIComponent(lmId)}/chunks`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    expandedChunks.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取切片详情失败: ${e.message}`)
    expandedChunks.value = []
  } finally {
    loadingChunks.value = false
  }
}

async function handleDeleteLandmark(lmId, lmName) {
  try {
    await ElMessageBox.confirm(
      `确定要从向量数据库中删除地标"${lmName}"的所有切片数据吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger', type: 'warning' }
    )
  } catch { return }

  try {
    const resp = await fetch(`/api/rag/landmarks/${encodeURIComponent(lmId)}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success(`已删除地标"${lmName}"的所有数据`)
    if (expandedLandmarkId.value === lmId) {
      expandedLandmarkId.value = null
      expandedChunks.value = []
    }
    await fetchLandmarks()
  } catch (e) {
    ElMessage.error(`删除失败: ${e.message}`)
  }
}

async function handleClearDatabase() {
  try {
    await ElMessageBox.confirm(
      '确定要清空 RAG 向量数据库吗？清空后已录入的所有地标切片数据均会丢失。',
      '危险操作确认',
      { confirmButtonText: '确定清空', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger', type: 'warning' }
    )
  } catch { return }

  loadingLandmarks.value = true
  try {
    const resp = await fetch('/api/rag/clear', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('向量数据库已清空')
    dbLandmarks.value = []
    expandedLandmarkId.value = null
    expandedChunks.value = []
  } catch (e) {
    ElMessage.error(`清空失败: ${e.message}`)
  } finally {
    loadingLandmarks.value = false
  }
}

// ---- 运行日志 ----
const logs = ref([])
const loadingLogs = ref(false)
const expandedLogIdx = ref(null)

async function fetchLogs() {
  loadingLogs.value = true
  expandedLogIdx.value = null
  try {
    const resp = await fetch('/api/rag/logs')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    logs.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取运行日志失败: ${e.message}`)
  } finally {
    loadingLogs.value = false
  }
}

function toggleLogExpand(idx) {
  expandedLogIdx.value = expandedLogIdx.value === idx ? null : idx
}

async function handleClearLogs() {
  try {
    await ElMessageBox.confirm('确定要清空所有运行日志吗？', '确认清空',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
  } catch { return }

  loadingLogs.value = true
  try {
    const resp = await fetch('/api/rag/logs/clear', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('运行日志已清空')
    logs.value = []
  } catch (e) {
    ElMessage.error(`清空日志失败: ${e.message}`)
  } finally {
    loadingLogs.value = false
  }
}

function getLogTagType(type) {
  const map = { ingest: 'success', recall: '', pending: 'warning', reject: 'danger', delete: 'danger' }
  return map[type] || 'info'
}

function getLogLabel(type) {
  const map = { ingest: '写入', recall: '召回', pending: '暂存', reject: '拒绝', delete: '删除' }
  return map[type] || type
}

// ---- 召回测试 ----
const recallQuery = ref('')
const recallSearching = ref(false)
const recallSearched = ref(false)
const recallResults = ref([])

async function handleRecallSearch() {
  if (!recallQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  recallSearching.value = true
  recallSearched.value = true
  try {
    const resp = await fetch(`/api/rag/query?query=${encodeURIComponent(recallQuery.value.trim())}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    recallResults.value = await resp.json()
  } catch (e) {
    ElMessage.error(`召回测试失败: ${e.message}`)
  } finally {
    recallSearching.value = false
  }
}

function getScoreType(score) {
  if (score === -1) return 'info'
  if (score >= 0.8) return 'success'
  if (score >= 0.5) return 'warning'
  return 'danger'
}

// ---- Agent 追踪 ----
const agentTraces = ref([])
const loadingTraces = ref(false)
const selectedRunId = ref(null)
const selectedTrace = ref(null)
const loadingTraceDetail = ref(false)
const expandedSteps = ref({})  // {stepId: bool}

async function fetchAgentTraces() {
  loadingTraces.value = true
  try {
    const resp = await fetch('/api/agent/traces')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    agentTraces.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取 Agent 追踪失败: ${e.message}`)
  } finally {
    loadingTraces.value = false
  }
}

async function selectAgentRun(runId) {
  selectedRunId.value = runId
  selectedTrace.value = null
  expandedSteps.value = {}
  loadingTraceDetail.value = true
  try {
    const resp = await fetch(`/api/agent/trace/${encodeURIComponent(runId)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const trace = await resp.json()
    // 给每个 step 分配一个稳定 id，用于展开状态映射
    ;(trace.steps || []).forEach((s, i) => { s._id = `${runId}_${i}` })
    selectedTrace.value = trace
  } catch (e) {
    ElMessage.error(`加载 Trace 详情失败: ${e.message}`)
  } finally {
    loadingTraceDetail.value = false
  }
}

// 按节点分组（保持步骤原始顺序）：连续同 node 的步骤归到一个 group，
// 节点切换时开启新 group，便于按"4 个 Agent 节点"的视角阅读。
const groupedSteps = computed(() => {
  if (!selectedTrace.value) return []
  const groups = []
  let current = null
  for (const step of selectedTrace.value.steps || []) {
    if (!current || current.node !== step.node) {
      current = { node: step.node || '(unknown)', steps: [] }
      groups.push(current)
    }
    current.steps.push(step)
  }
  return groups
})

function toggleStep(stepId) {
  expandedSteps.value[stepId] = !expandedSteps.value[stepId]
}

function getRunStatusType(status) {
  if (status === 'success') return 'success'
  if (status === 'error') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function getRunStatusLabel(status) {
  const map = { success: '成功', error: '失败', running: '运行中' }
  return map[status] || status
}

function getStepTagType(type) {
  const map = { llm_call: '', tool_call: 'success', event: 'warning', status: 'info', node_start: 'warning', node_end: 'warning' }
  return map[type] || ''
}

function getStepTypeLabel(type) {
  const map = {
    llm_call: 'LLM',
    tool_call: 'TOOL',
    event: 'EVENT',
    status: 'STATUS',
    node_start: '节点开始',
    node_end: '节点结束'
  }
  return map[type] || type
}

function formatRunTime(t) {
  if (!t) return ''
  // 输入形如 "2026-06-23 14:25:31.234"，只显示日期 + 时分秒
  return t.split('.')[0]
}

function formatDuration(ms) {
  if (!ms && ms !== 0) return ''
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.round(ms / 100) / 10
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return `${minutes}m ${rest}s`
}

function isExpandableStep(step) {
  return step.type === 'llm_call' || step.type === 'tool_call' || step.type === 'event'
}

function getStepPreview(step) {
  if (step.type === 'llm_call') return step.response_preview || step.summary || ''
  if (step.type === 'tool_call') return step.result_preview || step.summary || ''
  if (step.type === 'event') return step.details_preview || step.summary || ''
  return ''
}

function getPromptText(prompt) {
  if (prompt == null) return ''
  if (typeof prompt === 'string') return prompt
  try { return JSON.stringify(prompt, null, 2) } catch { return String(prompt) }
}

function formatStepResult(result) {
  if (result == null) return '(空)'
  if (typeof result === 'string') return result
  try { return JSON.stringify(result, null, 2) } catch { return String(result) }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选中文本')
  }
}

async function handleClearTraces() {
  try {
    await ElMessageBox.confirm('确定清空所有 Agent 追踪记录吗？此操作不可恢复。', '确认清空',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    const resp = await fetch('/api/agent/traces/clear', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('Agent 追踪记录已清空')
    agentTraces.value = []
    selectedRunId.value = null
    selectedTrace.value = null
  } catch (e) {
    ElMessage.error(`清空失败: ${e.message}`)
  }
}

// ---- 工具函数 ----
function formatUrl(url) {
  try { return new URL(url).hostname } catch { return url?.slice(0, 30) || '' }
}

// ---- 初始化 ----
onMounted(() => {
  fetchPending()
})
</script>

<style scoped>
.admin-panel {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: var(--bg-color);
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
}

/* ---- 顶部栏 ---- */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 60px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border-bottom: 1px solid rgba(208, 215, 222, 0.5);
  flex-shrink: 0;
}

.admin-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-color);
  font-size: 16px;
}
.back-btn:hover {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
  transform: translateX(-2px);
}

.admin-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.admin-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(60, 97, 75, 0.08);
  padding: 2px 10px;
  border-radius: 20px;
}

.admin-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
}
.status-dot.active {
  background: #52c41a;
  box-shadow: 0 0 6px rgba(82, 196, 26, 0.5);
  animation: pulse-dot 2s infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ---- 主体 ---- */
.admin-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ---- 左侧导航 ---- */
.admin-nav {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 20px 12px;
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(20px);
  border-right: 1px solid rgba(208, 215, 222, 0.4);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  transition: all 0.2s;
  position: relative;
}
.nav-item:hover {
  background: rgba(60, 97, 75, 0.06);
  color: var(--text-color);
}
.nav-item.active {
  background: rgba(60, 97, 75, 0.1);
  color: var(--primary-color);
  font-weight: 600;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: var(--primary-color);
  border-radius: 0 3px 3px 0;
}

.nav-label { flex: 1; text-align: left; }

.nav-badge {
  background: #ff4d4f;
  color: white;
  font-size: 11px;
  font-weight: 600;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 10px;
  padding: 0 5px;
}

/* ---- 右侧内容区 ---- */
.admin-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 24px 32px;
}

.tab-panel {
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.panel-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-color);
}

.panel-actions {
  display: flex;
  gap: 8px;
}

/* ---- 通用状态 ---- */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 0;
  color: var(--text-secondary);
  font-size: 14px;
}
.loading-state.compact {
  padding: 20px 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  text-align: center;
}
.empty-icon { color: rgba(0, 0, 0, 0.12); }
.empty-title {
  margin-top: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}
.empty-desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 400px;
  line-height: 1.6;
}

/* ---- 待审核卡片网格 ---- */
.pending-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.pending-card {
  padding: 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.5);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s;
}
.pending-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 16px rgba(60, 97, 75, 0.1);
  transform: translateY(-2px);
}
.pending-card.selected {
  border-color: var(--primary-color);
  background: rgba(60, 97, 75, 0.04);
  box-shadow: 0 0 0 2px rgba(60, 97, 75, 0.2);
}

.pending-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.pending-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
}
.pending-card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.pending-bangumi { font-weight: 500; }

.pending-sources {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.source-label { color: var(--text-secondary); }
.source-url {
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 6px;
  border-radius: 4px;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-more {
  color: var(--primary-color);
  font-weight: 500;
}

/* ---- 切片编辑区 ---- */
.chunk-editor-section {
  margin-top: 24px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(208, 215, 222, 0.5);
  border-radius: 14px;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.editor-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}

.chunks-list {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-card {
  padding: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  flex-shrink: 0;
}

.chunk-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.chunk-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
}

.editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

/* ---- 已入库地标 ---- */
.db-stats-bar {
  display: flex;
  gap: 32px;
  margin-bottom: 20px;
  padding: 16px 24px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary-color);
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.db-landmark-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.db-landmark-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.db-landmark-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.db-lm-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  cursor: pointer;
}
.db-lm-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.db-lm-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}
.db-lm-bangumi {
  font-size: 12px;
  color: var(--text-secondary);
}
.db-lm-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.expand-arrow {
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.expand-arrow.rotated { transform: rotate(90deg); }

.db-lm-detail {
  padding: 0 16px 16px;
  border-top: 1px solid var(--border-color);
}
.detail-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

/* ---- 通用切片列表 ---- */
.detail-chunk-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.detail-chunk-item {
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.02);
  border: 1px solid rgba(208, 215, 222, 0.3);
  border-radius: 8px;
}
.chunk-idx {
  font-size: 11px;
  font-weight: 600;
  color: var(--primary-color);
  margin-bottom: 4px;
  display: block;
}
.chunk-text {
  font-size: 13px;
  color: var(--text-color);
  line-height: 1.6;
  word-break: break-all;
  margin: 4px 0 0;
}
.chunk-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.chunk-source-tag {
  font-size: 11px;
  color: var(--text-secondary);
}
.chunks-badge {
  font-size: 12px;
  color: var(--primary-color);
  font-weight: 500;
  margin-left: 8px;
}

/* ---- 日志 ---- */
.logs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 10px;
  overflow: hidden;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.log-header:hover { background: rgba(0, 0, 0, 0.02); }

.log-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.log-title {
  font-size: 13px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-type-tag {
  flex-shrink: 0;
}
.log-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.log-time {
  font-size: 12px;
  color: var(--text-secondary);
}
.log-arrow {
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.log-arrow.rotated { transform: rotate(90deg); }

.log-detail {
  padding: 0 16px 16px;
  border-top: 1px solid rgba(208, 215, 222, 0.3);
}

.detail-section {
  margin-top: 12px;
}
.detail-section-title {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.detail-error {
  margin-top: 12px;
  padding: 10px;
  background: rgba(245, 108, 108, 0.08);
  border-radius: 6px;
  font-size: 13px;
}
.error-label { color: #f56c6c; font-weight: 600; }
.error-text { color: var(--text-color); margin-left: 6px; }

.context-pre {
  padding: 12px;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(208, 215, 222, 0.3);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 8px;
}

/* ---- 召回测试 ---- */
.recall-search-bar {
  margin-bottom: 24px;
}

.recall-meta {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.recall-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.recall-card {
  padding: 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  transition: box-shadow 0.2s;
}
.recall-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.recall-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.recall-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recall-rank {
  font-size: 14px;
  font-weight: 700;
  color: var(--primary-color);
}
.recall-source {
  font-size: 13px;
  color: var(--text-secondary);
}

.recall-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-color);
  word-break: break-all;
  margin: 0;
}

.recall-footer {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}
.recall-footer .source-label { margin-right: 4px; }
.recall-footer .source-val { opacity: 0.7; }

/* 滚动条 */
.admin-main::-webkit-scrollbar,
.logs-list::-webkit-scrollbar,
.chunks-list::-webkit-scrollbar {
  width: 6px;
}
.admin-main::-webkit-scrollbar-track,
.logs-list::-webkit-scrollbar-track,
.chunks-list::-webkit-scrollbar-track {
  background: transparent;
}
.admin-main::-webkit-scrollbar-thumb,
.logs-list::-webkit-scrollbar-thumb,
.chunks-list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 3px;
}
.admin-main::-webkit-scrollbar-thumb:hover,
.logs-list::-webkit-scrollbar-thumb:hover,
.chunks-list::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}

/* ============ Agent 追踪 Tab ============ */
.agent-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  margin: -8px 0 16px;
  padding: 8px 12px;
  background: rgba(60, 97, 75, 0.05);
  border-radius: 8px;
}

.agent-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 260px);
  min-height: 480px;
}

.agent-runs-pane {
  width: 280px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  padding: 12px;
  overflow-y: auto;
}

.agent-runs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-run-card {
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s;
}
.agent-run-card:hover {
  border-color: var(--primary-color);
  transform: translateY(-1px);
}
.agent-run-card.active {
  background: rgba(60, 97, 75, 0.08);
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(60, 97, 75, 0.15);
}
.agent-run-card.error {
  border-left: 3px solid #f56c6c;
}
.agent-run-card.running {
  border-left: 3px solid #e6a23c;
}

.run-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.run-steps-count {
  font-size: 11px;
  color: var(--text-secondary);
}
.run-card-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.run-days {
  font-weight: 600;
  color: var(--primary-color);
}
.run-card-landmarks {
  font-size: 12px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-card-tools {
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--primary-color);
  background: rgba(60, 97, 75, 0.06);
  border-radius: 4px;
  padding: 3px 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.more-tag {
  color: var(--primary-color);
  font-size: 10px;
  margin-left: 2px;
}
.run-card-error {
  margin-top: 6px;
  padding: 4px 6px;
  font-size: 11px;
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.08);
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-detail-pane {
  flex: 1;
  min-width: 0;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  padding: 20px;
  overflow-y: auto;
}

.agent-trace-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.trace-overview {
  padding: 12px 14px;
  background: rgba(60, 97, 75, 0.04);
  border: 1px solid rgba(60, 97, 75, 0.12);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.overview-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-color);
  flex-wrap: wrap;
}
.overview-label {
  color: var(--text-secondary);
  margin-right: 2px;
}
.overview-code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 6px;
  border-radius: 4px;
}
.overview-error {
  margin-top: 4px;
  padding: 8px 10px;
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
  font-size: 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}

.node-group {
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 10px;
  overflow: hidden;
}

.node-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(60, 97, 75, 0.06);
  border-bottom: 1px solid rgba(208, 215, 222, 0.3);
}
.node-group-icon {
  color: var(--primary-color);
}
.node-group-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--primary-color);
  flex: 1;
}
.node-group-count {
  font-size: 11px;
  color: var(--text-secondary);
}

.step-timeline {
  padding: 10px 0;
  display: flex;
  flex-direction: column;
}

.step-item {
  display: flex;
  gap: 10px;
  padding: 8px 14px;
}

.step-marker {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 2px;
}
.step-llm_call .step-marker { background: rgba(60, 97, 75, 0.15); color: #3c614b; }
.step-tool_call .step-marker { background: rgba(103, 194, 58, 0.15); color: #67c23a; }
.step-event .step-marker { background: rgba(230, 162, 60, 0.15); color: #e6a23c; }
.step-status .step-marker { background: rgba(144, 147, 153, 0.15); color: #909399; }
.step-node_start .step-marker,
.step-node_end .step-marker { background: rgba(230, 162, 60, 0.15); color: #e6a23c; }

.step-body {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  border-radius: 6px;
  padding: 4px 8px;
  margin: -4px -8px;
  transition: background 0.15s;
}
.step-body:hover {
  background: rgba(0, 0, 0, 0.02);
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-preview {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.025);
  border-radius: 6px;
  padding: 6px 8px;
  word-break: break-word;
}
.step-title {
  flex: 1;
  font-size: 13px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-time {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Consolas', monospace;
}
.step-arrow {
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.step-arrow.rotated { transform: rotate(90deg); }
.step-error-tag {
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
  border-radius: 4px;
}

.step-detail {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: default;
}

.io-block {
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.7);
}
.io-label {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.025);
  border-bottom: 1px solid rgba(208, 215, 222, 0.3);
}
.io-label-error { color: #f56c6c; }
.io-meta {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 6px;
  border-radius: 4px;
}
.copy-btn {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}
.copy-btn:hover {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.io-pre {
  margin: 0;
  padding: 10px 12px;
  font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-color);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
  background: transparent;
}
.io-pre-error {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.05);
}

.empty-state.compact {
  padding: 40px 16px;
}
.empty-state.compact .empty-desc {
  margin-top: 8px;
  font-size: 12px;
}

.agent-runs-pane::-webkit-scrollbar,
.agent-detail-pane::-webkit-scrollbar,
.io-pre::-webkit-scrollbar {
  width: 6px;
}
.agent-runs-pane::-webkit-scrollbar-thumb,
.agent-detail-pane::-webkit-scrollbar-thumb,
.io-pre::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 3px;
}

.admin-header { height: 78px; background: var(--surface-color); border-color: var(--border-color); }
.admin-title { font-weight: 600; letter-spacing: 1px; }
.admin-subtitle { border-radius: 6px; font-size: 10px; padding: 5px 9px; }
.status-text { font-size: 9px; letter-spacing: 1.7px; color: #8f9b82; }
.admin-nav { background: #eef0e6; border-color: var(--border-color); }
.admin-main { padding: 28px 32px; }
.nav-item { font-size: 12px; padding: 14px; }
.nav-item.active { background: #dfe8d5; }
.pending-card, .db-landmark-card, .log-card, .recall-card, .agent-runs-pane, .agent-detail-pane { background: var(--surface-color); border-color: var(--border-color); }
@media (max-width: 820px) {
  .admin-header { height: 66px; padding: 0 16px; }
  .admin-header-left { gap: 11px; }
  .admin-title { font-size: 16px; }
  .admin-subtitle, .admin-header-right { display: none; }
  .admin-body { flex-direction: column; }
  .admin-nav { flex-direction: row; overflow-x: auto; width: 100%; padding: 10px; border-right: 0; border-bottom: 1px solid var(--border-color); gap: 4px; }
  .nav-item { font-size: 11px; padding: 10px 12px; white-space: nowrap; flex-shrink: 0; gap: 7px; }
  .nav-item.active::before { display: none; }
  .admin-main { padding: 20px 16px; }
  .panel-header { flex-wrap: wrap; gap: 12px; }
  .panel-title { font-size: 18px; }
  .pending-grid { grid-template-columns: 1fr; }
  .agent-layout { flex-direction: column; height: auto; }
  .agent-runs-pane { width: 100%; max-height: 260px; }
  .agent-detail-pane { min-height: 280px; }
  .editor-modal { width: calc(100vw - 24px); }
}
</style>
